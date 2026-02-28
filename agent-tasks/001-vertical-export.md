# Task 001: Vertical Export (9:16, 1:1)

**Priority:** 🔴 CRITICAL
**Effort:** 3 days
**Status:** ✅ IMPLEMENTATION COMPLETE (Testing Pending)
**Depends on:** Nothing
**Assigned to:** —

---

## Goal

Add aspect ratio selection to video export. Currently only 16:9. Need 9:16 (TikTok/Reels/Shorts) and 1:1 (Instagram feed).

## Why This Matters

- 80% of target distribution is vertical (TikTok, Reels, Shorts)
- Users shoot vertical on phone → we output horizontal = wrong
- Easiest ship-blocker to fix (3 days vs 2 weeks for audio)

## What To Change

### Backend Changes

#### 1. `backend/app/services/video_stitcher.py` — Add crop filter

Current `stitch_clips_v2()` builds a filter_complex with trim + speed + concat.

**Add aspect ratio crop AFTER concat, BEFORE output:**

```python
# After concat filter, add crop+scale:
# 9:16 → crop center to 9:16 ratio, then scale to 1080x1920
# 1:1  → crop center to square, then scale to 1080x1080
# 16:9 → no crop needed (current behavior)

# Smart crop: cooking content → food is usually center-bottom of frame
# For 9:16 from 16:9 source: crop width to 9/16 of height, center horizontally
# Filter: crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920
```

**Function signature change:**
```python
def stitch_clips_v2(clip_entries, output_path, aspect_ratio="16:9"):
```

#### 2. `backend/app/services/proxy_renderer.py` — Proxy aspect ratio

`pre_render_proxy_clips()` renders at 480p. Need to respect aspect ratio for proxy preview too.

For 9:16 proxy: `scale=-2:480` → `crop=ih*9/16:ih,scale=270:480`

#### 3. `backend/app/routers/edit_plan.py` — API accepts aspect_ratio

- `confirm_and_render()` endpoint: accept `aspect_ratio` param
- `refine` endpoint: pass aspect_ratio when re-rendering proxy
- Store in edit_plan document in MongoDB

#### 4. `backend/app/services/pipeline.py` — Pipeline uses project aspect_ratio

- Read `aspect_ratio` from project document
- Pass to stitch_clips_v2 and proxy_renderer

#### 5. `backend/app/routers/projects.py` — Project creation accepts aspect_ratio

- Add `aspect_ratio` field to project model (default "16:9")

### Frontend Changes

#### 6. `frontend/app/dashboard/new/page.tsx` — Aspect ratio selector in project creation

Add toggle/button group: 16:9 | 9:16 | 1:1
Visual preview of each (phone shape, landscape, square)

#### 7. `frontend/app/dashboard/project/[id]/page.tsx` — Format selector on export

Add dropdown/buttons near download button: "Export as: 16:9 | 9:16 | 1:1"
Allow re-export in different format without re-running pipeline

#### 8. `frontend/lib/api.ts` — API types update

Add aspect_ratio to Project type and relevant API calls

### Testing

#### 9. Test with actual videos
- Upload vertical iPhone video (portrait MOV with rotation=-90 metadata)
- Generate → should detect orientation
- Export as 9:16 → should look correct on phone
- Export as 1:1 → should be square, food centered
- Export as 16:9 → should match current behavior (no regression)

---

## Checklist

- [x] Backend: Add aspect_ratio param to `stitch_clips_v2()`
- [x] Backend: Add crop filter logic for 9:16 and 1:1
- [x] Backend: Smart center crop (not just geometric center)
- [x] Backend: Update proxy renderer for aspect ratio
- [x] Backend: API endpoint accepts aspect_ratio
- [x] Backend: Store aspect_ratio in project + edit_plan
- [x] Frontend: Aspect ratio selector on project creation
- [x] Frontend: Format selector on export/download
- [x] Frontend: API types updated
- [ ] Test: 9:16 export from landscape source
- [ ] Test: 9:16 export from portrait source
- [ ] Test: 1:1 export
- [ ] Test: 16:9 still works (no regression)

## Technical Notes

- Source videos are portrait (1920x1080 with rotation=-90 metadata) — ffmpeg auto-rotates
- After auto-rotate, effective dimensions are 1080x1920 (already vertical!)
- So for 9:16 from vertical source → might just need scale, no crop
- For 9:16 from horizontal source → crop center
- Test BOTH scenarios

## ffmpeg Reference

```bash
# Crop 16:9 to 9:16 (center crop)
ffmpeg -i input.mp4 -vf "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920" output.mp4

# Crop to 1:1 (center square)
ffmpeg -i input.mp4 -vf "crop=min(iw\,ih):min(iw\,ih),scale=1080:1080" output.mp4

# Smart crop with slight bottom offset (food on counter)
ffmpeg -i input.mp4 -vf "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920" output.mp4
```

## Decision Log
- **Why crop, not letterbox?** Letterbox (black bars) looks amateur on social media. Crop is what pros do.
- **Why center crop, not smart AI crop?** Start simple, add AI crop later (Claude Vision detect food position). Center works 80% of time for cooking (food in center of frame).
