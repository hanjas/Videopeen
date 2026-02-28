# Task 006: Transitions - Verification Guide

This document provides test scenarios to verify the transition implementation works correctly.

---

## Quick Verification

### 1. Check Default Behavior (Backward Compatibility)

**Test:** Create a new project without specifying transition fields
**Expected:** Project should use fade transitions with 0.5s duration by default

```python
# In MongoDB shell or via API
db.projects.findOne({_id: "<project_id>"})

# Should show:
{
  ...
  "transition_type": "fade",
  "transition_duration": 0.5,
  ...
}
```

### 2. Test Hard Cuts (No Transitions)

**Create a project with:**
```json
{
  "transition_type": "none",
  "transition_duration": 0.0
}
```

**Expected:**
- Video should have hard cuts between clips (no fade/dissolve)
- Audio should have hard cuts (no crossfade)
- ffmpeg filter should use `concat` not `xfade`

**How to verify:**
- Check backend logs for "concat=n=" (not "xfade")
- Watch rendered video - should see instant cuts

### 3. Test Fade Transitions

**Create a project with:**
```json
{
  "transition_type": "fade",
  "transition_duration": 0.5
}
```

**Expected:**
- Smooth fade/dissolve between clips
- Audio should crossfade smoothly
- Final duration should be shorter due to overlaps

**How to verify:**
- Check backend logs for "xfade=transition=fade:duration=0.5"
- Check backend logs for "acrossfade=d=0.5"
- Watch rendered video - should see smooth fades

---

## Detailed Test Scenarios

### Scenario 1: Three Clips with Fade

**Setup:**
- 3 clips: 6s, 5s, 4s (after speed adjustments)
- transition_type: "fade"
- transition_duration: 0.5s

**Expected Output:**
- Total duration: `6 + 5 + 4 - 2*0.5 = 14s` (not 15s)
- First transition at 5.5s mark (6.0 - 0.5)
- Second transition at 10.0s mark (6.0 + 5.0 - 2*0.5)

**Filter chain should look like:**
```
[v0][v1]xfade=transition=fade:duration=0.5:offset=5.5[xf1];
[xf1][v2]xfade=transition=fade:duration=0.5:offset=10.0[concat]

[a0][a1]acrossfade=d=0.5:c1=tri:c2=tri[af1];
[af1][a2]acrossfade=d=0.5:c1=tri:c2=tri[aconcat]
```

### Scenario 2: Different Transition Types

Test each transition type:
- **fade** — Classic dissolve
- **wiperight** — Wipe from left to right
- **slideright** — Slide from left to right  
- **smoothleft** — Smooth slide from right to left

**Expected:**
Each should produce different visual effects but same audio crossfade.

**How to verify:**
- Check logs for `xfade=transition=<type>`
- Watch rendered videos - visual transitions should differ

### Scenario 3: Speed Ramps + Transitions

**Setup:**
- 2 clips with speed adjustments (e.g., 2x and 0.5x)
- transition_type: "fade"
- transition_duration: 0.5s

**Expected:**
- Offset calculation should use effective duration (original / speed)
- Audio should be speed-adjusted BEFORE crossfade
- No audio sync issues

**How to verify:**
- Check logs for correct offset calculation
- Watch video - audio/video should stay in sync through transition

### Scenario 4: Different Aspect Ratios

Test each aspect ratio with transitions:
- **9:16** (vertical - TikTok)
- **1:1** (square - Instagram)
- **16:9** (landscape - YouTube)

**Expected:**
- Transitions work correctly for all aspect ratios
- Aspect ratio crop should be applied AFTER transitions
- No weird scaling/cropping during transitions

**Filter order should be:**
```
xfade chain → [concat] → aspect ratio crop → [outv]
```

### Scenario 5: Very Short Clips

**Setup:**
- Clip duration < transition_duration
- E.g., 0.3s clip with 0.5s transition

**Expected:**
- Should log warning about negative offset
- Offset should be clamped to 0
- Video should still render (no crash)

**How to verify:**
- Check logs for "Negative xfade offset" warning
- Video should render without errors

---

## Audio Verification

### Test 1: Audio Crossfade Quality

**Listen for:**
- Smooth volume transition (no sudden jumps)
- No audio gaps or pops
- Background music should fade seamlessly

### Test 2: Audio Sync

**Watch for:**
- Voiceover should stay in sync with video during transition
- No drift between audio and video
- Crossfade should match video transition timing

### Test 3: Silent Clips

**Setup:**
- Mix clips with audio and clips without audio
- transition_type: "fade"

**Expected:**
- Silent clips should generate null audio
- Crossfade should still work (fade to/from silence)
- No audio errors in logs

---

## Regression Testing

### Verify No Breaking Changes

1. **Aspect Ratio Crops (Task 001)**
   - [ ] 9:16 vertical crop still works
   - [ ] 1:1 square crop still works
   - [ ] 16:9 landscape crop still works
   - [ ] Crop is applied AFTER transitions

2. **Audio Processing (Task 002)**
   - [ ] atempo filter chain for speed adjustments
   - [ ] Silent audio generation for clips without audio
   - [ ] loudnorm filter for audio normalization
   - [ ] Audio normalization is applied AFTER crossfades

3. **Speed Ramps**
   - [ ] Speed factors (2x, 0.5x) still work
   - [ ] Chained atempo filters for quality
   - [ ] Effective duration calculation correct

---

## Logs to Check

### Successful Render with Transitions

Look for these in backend logs:

```
INFO:app.services.video_stitcher:Stitching 3 clips from 2 sources → /path/to/output.mp4
```

Filter complex should contain:
- `xfade=transition=fade:duration=0.5:offset=...` (N-1 times for N clips)
- `acrossfade=d=0.5:c1=tri:c2=tri` (N-1 times)
- `crop='min(iw,ih*...)...scale=...` (aspect ratio crop AFTER xfade)
- `loudnorm=I=-14:TP=-1:LRA=11` (audio norm AFTER acrossfade)

### Successful Render without Transitions

Look for:
```
concat=n=3:v=1:a=0[concat]
concat=n=3:v=0:a=1[aconcat]
```

No `xfade` or `acrossfade` should appear.

---

## Performance Benchmarks

### With Transitions (fade, 0.5s)
- Expected: ~5-10% slower than hard cuts
- Reason: xfade/acrossfade require blending frames

### Without Transitions (none)
- Expected: Same as before (no regression)
- Reason: Falls back to simple concat

**Test:**
1. Render same project with `transition_type="none"` → measure time
2. Render same project with `transition_type="fade"` → measure time
3. Compare (should be similar, within 10%)

---

## Edge Cases

### 1. Single Clip
- **Expected:** No transitions applied (N-1 = 0)
- **Result:** Should render normally

### 2. Empty Clip List
- **Expected:** Raise ValueError before reaching transition logic
- **Result:** Should not crash

### 3. Negative Durations
- **Expected:** Skipped in trim loop, never reach transition logic
- **Result:** Should not crash

### 4. Very Long Transitions (> clip duration)
- **Expected:** Negative offset warning, clamped to 0
- **Result:** Should render (may look weird but shouldn't crash)

### 5. Mixed Source Formats
- **Expected:** All normalized to yuv420p before xfade
- **Result:** Should work (already handled by format filter)

---

## Quick Test Command

To manually test the filter chain:

```bash
ffmpeg -y \
  -i clip1.mp4 -i clip2.mp4 \
  -filter_complex "\
    [0:v]trim=start=0:end=5,setpts=PTS-STARTPTS,format=yuv420p[v0];\
    [1:v]trim=start=0:end=5,setpts=PTS-STARTPTS,format=yuv420p[v1];\
    [0:a]atrim=start=0:end=5,asetpts=PTS-STARTPTS[a0];\
    [1:a]atrim=start=0:end=5,asetpts=PTS-STARTPTS[a1];\
    [v0][v1]xfade=transition=fade:duration=0.5:offset=4.5[vout];\
    [a0][a1]acrossfade=d=0.5:c1=tri:c2=tri[aout]" \
  -map "[vout]" -map "[aout]" \
  -c:v h264_videotoolbox -b:v 12M \
  -c:a aac -b:a 192k \
  output.mp4
```

Expected: 9.5s video (5 + 5 - 0.5) with fade transition at 4.5s

---

## Sign-Off Checklist

Before marking as fully complete:

- [ ] All transition types tested (none, fade, wiperight, slideright, smoothleft)
- [ ] All aspect ratios work with transitions (9:16, 1:1, 16:9)
- [ ] Speed ramps + transitions = no audio sync issues
- [ ] Backward compatibility verified (old projects work)
- [ ] No regression in aspect ratio crops
- [ ] No regression in audio processing
- [ ] Edge cases handled gracefully (short clips, single clip, etc.)
- [ ] Performance impact acceptable (<10% slower)
- [ ] Frontend UI implemented (or documented as pending)
- [ ] User documentation updated

---

**Status:** Backend complete, ready for testing. Frontend UI still needed.
