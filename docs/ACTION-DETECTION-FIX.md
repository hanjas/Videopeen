# Action Detection Fix — Design Doc

## Problem
The action detection pipeline misses brief cooking actions (1-2 second spice additions). Empirically verified: garam masala added at ~140s was labeled as "idle" because the detection never saw the hand/spoon in frame.

## Root Cause (Empirically Verified)
Two independent failures:
1. **Frame capture gap** — At 1fps + motion filter, the 1-second window when a spoon enters, drops powder, and exits gets filtered out. The motion delta is too small (static camera, brief hand movement).
2. **Detection gap** — Even when Claude saw "brown spice powder visible on top" in later frames, it labeled the period as IDLE instead of flagging "new content appeared."

### Evidence (video 7689ed60)
- 139.5s: NO brown powder, NO hand
- **140.5s: Brown powder visible + spoon retreating** ← 1 second action window
- 142s+: Brown powder clearly present
- Detection labeled 129-169s as IDLE (40 seconds!)

## Solution: 3-Layer Fix

### Layer 1: Prompt Fix (Ship Day 1, 1 hour, $0 extra cost)

**1A: State-diff instruction** — Add to TIMELINE_SYSTEM prompt:
```
When marking a period as IDLE, compare the scene at the start vs end.
If ANY new ingredient, substance, or item has appeared that wasn't there before,
mark it as an ACTION with type "inferred_addition" and description
"[item] appeared — likely added between Xs-Ys" even if you didn't see the hand movement.
```

**1B: Recipe-aware ingredient tracking** — Enhance the prompt:
```
The recipe includes these ingredient additions: [list from recipe_steps].
Use this list to help identify ingredients by expected color/texture.
If you see fewer additions than expected, note which expected ingredients
were NOT observed — they may have been added outside the analyzed frames.
```

**1C: 1-frame batch overlap** — Include the last frame of the previous batch as the first frame of the next batch. Gives Claude context continuity across batch boundaries. Cost: ~13% more tokens per batch.

### Layer 2: 2fps + SSIM Scene Selection (Ship Day 2, 4 hours, +50% API cost)

Replace the current "1fps + motion filter" with:

**Phase 1: Extract at 2fps, no motion filter**
- ffmpeg extracts all frames at 2fps
- ~8,640 frames for 72 min footage (vs ~720 currently)
- Disk: ~430MB temp (cleaned after selection)

**Phase 2: SSIM-based scene segmentation + intelligent selection**
```python
# Downsample all frames to 256×256
# Compute pairwise SSIM between consecutive frames
# Segment into "scenes" using adaptive threshold

# Scene break detection (handles both tripod and handheld)
def is_scene_break(prev, curr, adaptive_threshold):
    full_ssim = compute_ssim(prev, curr)
    if full_ssim > adaptive_threshold:
        return False   # clearly same scene
    if full_ssim < adaptive_threshold - 0.10:
        return True    # clearly different scene
    # Ambiguous: check center crop (camera wobble affects edges, not center)
    center_ssim = compute_ssim_center_crop(prev, curr, crop_ratio=0.5)
    return center_ssim < adaptive_threshold

# Adaptive threshold per video
median_ssim = np.median(all_pairwise_ssim)
scene_threshold = max(0.85, median_ssim - 0.05)

# Frame selection per scene:
# < 2.0s duration: KEEP ALL FRAMES (brief action! Most important!)
# 2.0 - 5.0s: keep first, middle, last
# > 5.0s: keep first + last + 1 per 4s interior
# ALWAYS keep both frames at every scene boundary
```

**KEY INSIGHT**: Brief scenes get MORE frames, not fewer. This inverts the current bug where brief actions get filtered OUT.

**Expected output**: ~400-500 selected frames (vs ~316 currently), but with dramatically better coverage of brief actions.

### Layer 3: Reconciliation Phase (Ship Day 3, 2 hours, $0 extra cost)

After detection, compare detected actions against recipe ingredient list:
- For each recipe ingredient not found in detections, flag it
- Check if any "idle" period contains visual evidence of the missing ingredient
- Surface to user: "Garam masala expected but not clearly detected. Nearest match: brown powder at 140s."

### Bonus: Whisper Integration (Day 3-4, 2-3 hours, $0 — runs locally)

Run whisper.cpp (base model) locally on the audio track:
- If narration exists, inject timestamped transcript into detection prompt
- "Now add the garam masala" at 139s → Claude gets this context alongside the frames
- Graceful no-op when no useful narration detected

## Cost Impact

| Metric | Current | After Prompt Fix (Day 1) | After All Layers |
|--------|---------|--------------------------|------------------|
| Frames to API | ~316 | ~330 (+overlap) | ~450 |
| Vision API cost | $0.50-1.00 | $0.55-1.05 | **$0.75-1.50** |
| Total wall time | ~5 min | ~5 min | **~6 min** |

## Implementation Order

| # | Task | Effort | Day |
|---|------|--------|-----|
| 1 | State-diff prompt + recipe-aware prompt | 1h | Day 1 |
| 2 | 1-frame batch overlap | 1h | Day 1 |
| 3 | 2fps extraction + SSIM scene selection | 4h | Day 2 |
| 4 | Reconciliation phase | 2h | Day 3 |
| 5 | Whisper integration | 2-3h | Day 3-4 |
| 6 | Adaptive SSIM for handheld footage | 2h | Week 2 |

## Accepted Risks

| Risk | Mitigation |
|------|------------|
| Off-screen additions (no hand visible) | State-diff prompt detects content change; reconciliation flags it |
| SSIM over-segments handheld footage | Adaptive threshold + center-crop tiebreaker |
| 50% higher API cost | $0.75-1.50 still cheap; worth the quality gain |
| Whisper useless on non-narrated videos | Runs locally ($0), fails gracefully |

## Validation Plan

Before shipping SSIM (step 3), validate on the garam masala video:
```bash
ffmpeg -i video_7689ed60.mp4 -ss 127 -to 145 -vf fps=2 test_frames/f_%04d.jpg
# Verify: frame at ~140.5s shows spoon + brown powder
# Run SSIM selection, confirm both 140.0s and 140.5s frames are KEPT
# Confirm total selected frames: 400-500 range across all videos
```

## What NOT to Change

- **Keep Smart Clip Finding system** as defense-in-depth fallback (Layers 0-5)
- **Don't increase beyond 2fps** — diminishing returns, 2fps is empirically sufficient
- **Don't add histogram-based filtering** — SSIM is simpler and more robust
