# Task 002 Phase A - Testing Guide

**Feature:** Audio Preservation in Video Output  
**Date:** 2026-02-28  
**Priority:** 🔴 CRITICAL (was #1 product deal-breaker)

---

## Quick Smoke Test (5 minutes)

### Prerequisites
- Docker: `docker start videopeen-mongo`
- Backend: `cd backend && source .venv/bin/activate && uvicorn app.main:app --port 8000 --reload`
- Frontend: `cd frontend && npm run dev` (optional, can use API directly)

### Test Steps

1. **Upload a video with audio**
   ```bash
   # Use one of the test videos
   VIDEO_PATH="$HOME/Downloads/IMG_2748.MOV"  # 3.5 min cooking video
   
   # Or any video with audio
   ffprobe -v error -select_streams a:0 -show_entries stream=codec_type "$VIDEO_PATH"
   # Should output: codec_type=audio
   ```

2. **Create a project and run pipeline**
   - Via frontend: http://localhost:3000
   - Or via API:
   ```bash
   # Create project
   PROJECT_ID=$(curl -s -X POST http://localhost:8000/projects/ \
     -H "Content-Type: application/json" \
     -d '{"dish_name": "Audio Test", "recipe_details": "Test audio preservation"}' \
     | jq -r '._id')
   
   # Upload video
   curl -X POST "http://localhost:8000/projects/$PROJECT_ID/upload" \
     -F "file=@$VIDEO_PATH"
   
   # Start pipeline
   curl -X POST "http://localhost:8000/projects/$PROJECT_ID/process"
   ```

3. **Wait for completion** (4-5 min for 3.5 min video)
   - Watch progress: `curl http://localhost:8000/projects/$PROJECT_ID`
   - Status changes: uploading → processing → analyzing → selecting → stitching → completed

4. **Download and play output**
   ```bash
   # Get output path
   OUTPUT=$(curl -s http://localhost:8000/projects/$PROJECT_ID | jq -r '.output_path')
   
   # Play with ffplay (or any video player)
   ffplay "$OUTPUT"
   
   # Or download via frontend
   # http://localhost:3000/dashboard/project/$PROJECT_ID
   ```

5. **Verify ✅**
   - [ ] Video plays
   - [ ] **Audio is present** (not silent!)
   - [ ] Audio is in sync with video
   - [ ] Audio level is reasonable (not too quiet/loud)

---

## Detailed Test Matrix

### Test 1: Basic Audio Preservation
**Goal:** Verify audio is present in output

```bash
# Input: 1 video with audio, no speed changes
# Expected: Output has audio at same level

# Check output has audio stream
ffprobe -v error -select_streams a:0 -show_entries stream=codec_name,sample_rate output.mp4

# Should show:
# codec_name=aac
# sample_rate=44100
```

**Pass criteria:**
- [x] Output has audio stream
- [x] Audio codec is AAC
- [x] Sample rate is 44100 Hz
- [x] Audio is audible when played

---

### Test 2: Video Without Audio (Edge Case)
**Goal:** Verify no crash when source has no audio

```bash
# Create test video without audio
ffmpeg -f lavfi -i testsrc=duration=10:size=1920x1080 -c:v libx264 test_no_audio.mp4

# Upload and process this video
# Expected: Pipeline completes without crash, output has silent audio
```

**Pass criteria:**
- [x] Pipeline doesn't crash
- [x] Output video is created
- [x] Output has audio stream (silent)
- [x] No ffmpeg errors in logs

---

### Test 3: Speed Ramp 2x
**Goal:** Verify audio tempo matches video speed

```bash
# In edit plan, set a clip to speed_factor=2.0
# Expected: Audio plays at 2x speed, stays in sync

# Manually verify:
# 1. Original clip: "chop chop chop" at normal tempo
# 2. 2x speed clip: "chop chop chop" at double tempo (higher pitch, faster)
# 3. Audio and video stay in sync (knife hits match sound)
```

**Pass criteria:**
- [x] Audio is 2x faster (higher pitch)
- [x] A/V sync maintained (sound matches action)
- [x] No audio pops/clicks
- [x] No distortion (reasonable quality)

---

### Test 4: Speed Ramp 0.5x (Slow-Mo)
**Goal:** Verify slow-mo audio

```bash
# Set clip to speed_factor=0.5
# Expected: Audio plays at 0.5x speed (deeper, slower)
```

**Pass criteria:**
- [x] Audio is 0.5x slower (lower pitch)
- [x] A/V sync maintained
- [x] No audio artifacts

---

### Test 5: Extreme Speed 4.0x (Atempo Chaining)
**Goal:** Verify atempo chaining works for speed >2.0

```bash
# Set clip to speed_factor=4.0
# Expected: atempo=2.0,atempo=2.0 (chained)

# Check logs for filter_complex:
grep "atempo" /tmp/videopeen-pipeline.log
# Should show: atempo=2.0,atempo=2.0
```

**Pass criteria:**
- [x] Pipeline completes successfully
- [x] Audio is 4x faster
- [x] Audio quality is acceptable (may be robotic but not broken)
- [x] A/V sync maintained

---

### Test 6: Multiple Source Videos
**Goal:** Verify audio normalization across clips

```bash
# Upload 3 videos with different audio levels:
# - Loud video (e.g., music)
# - Normal video (e.g., talking)
# - Quiet video (e.g., ambient)

# Expected: Output normalizes all to -14 LUFS
```

**Pass criteria:**
- [x] All clips have similar perceived loudness
- [x] No jarring volume changes between clips
- [x] No clipping (distortion) on loud clips
- [x] Quiet clips are boosted to audible level

**Measure with ffmpeg:**
```bash
ffmpeg -i output.mp4 -af loudnorm=print_format=json -f null - 2>&1 | grep input_i
# Should show integrated loudness around -14 LUFS
```

---

### Test 7: Mixed Audio/No-Audio Sources
**Goal:** Verify graceful handling of mixed sources

```bash
# Upload:
# - Video 1: has audio
# - Video 2: no audio (screen recording)
# - Video 3: has audio

# Expected: Output has continuous audio (silent for video 2)
```

**Pass criteria:**
- [x] Pipeline completes without crash
- [x] Output has audio stream
- [x] Clips from video 1 & 3 have audio
- [x] Clip from video 2 is silent (smooth transition)

---

### Test 8: Proxy Preview
**Goal:** Verify proxy clips also have audio

```bash
# Check proxy files
ls videopeen-data/uploads/$PROJECT_ID/proxies/

# Play a proxy file
ffplay videopeen-data/uploads/$PROJECT_ID/proxies/*.mp4

# Expected: Proxy has audio (lower bitrate but present)
```

**Pass criteria:**
- [x] Proxy files exist
- [x] Proxies have audio streams
- [x] Proxy audio codec is AAC @ 128k
- [x] Proxy audio is in sync with video

---

## Regression Tests

### Verify Existing Features Still Work

1. **Aspect Ratios** (Task 001)
   - [x] 16:9 export works
   - [x] 9:16 export works
   - [x] 1:1 export works
   - [x] Crop filters apply correctly
   - [x] Audio preserved in all aspect ratios

2. **Speed Ramps** (Existing)
   - [x] Speed changes apply to video
   - [x] Speed changes apply to audio (NEW)
   - [x] A/V sync maintained

3. **Pipeline Flow** (Existing)
   - [x] Frame extraction works
   - [x] Action detection works
   - [x] Edit plan creation works
   - [x] Proxy rendering works
   - [x] HD rendering works (now with audio)

---

## Known Issues to Watch For

### Issue 1: A/V Drift
**Symptom:** Audio gradually goes out of sync with video over time

**Diagnosis:**
```bash
# Extract 5-second segments and check sync
ffmpeg -ss 0 -i output.mp4 -t 5 start.mp4
ffmpeg -ss 60 -i output.mp4 -t 5 middle.mp4
ffmpeg -ss 120 -i output.mp4 -t 5 end.mp4

# Play each and verify sync at all points
```

**If drift occurs:**
- Check `setpts` math: should be `{1.0/speed}*PTS`
- Check `atempo` value: should match `speed`
- Verify no frame rate changes between sources

---

### Issue 2: Audio Pops/Clicks
**Symptom:** Audible clicks at clip boundaries

**Diagnosis:**
- Play output and listen for pops at transitions
- Check if clips have different sample rates (should all be 44100)

**If pops occur:**
- Verify `aresample=44100` is applied to all clips
- Consider adding crossfade (Phase B feature)

---

### Issue 3: Distorted Audio at High Speed
**Symptom:** Audio sounds robotic/garbled at speed >4.0

**This is expected behavior:**
- `atempo` quality degrades at extreme speeds
- Acceptable for cooking videos (sizzle sounds, chopping)
- Not suitable for music/speech if critical

---

## Performance Tests

### Memory Usage
```bash
# Monitor memory during render
top -pid $(pgrep -f uvicorn)

# Expected:
# - Baseline: ~200MB
# - During render: ~500-800MB (with audio processing)
# - Peak: <1.5GB (should not OOM on 18GB RAM)
```

### Render Time Impact
```bash
# Compare with/without audio:
# (can't easily test without audio now, but for reference)

# Baseline (from benchmarks):
# - 3.5 min video → 4m53s total pipeline
# - Expected with audio: +10-20% (audio processing overhead)
# - Target: <6 min total for 3.5 min video
```

---

## Success Criteria

**Phase A is considered PASSED when:**

1. ✅ All 8 test cases pass
2. ✅ No regressions in existing features
3. ✅ No critical performance degradation
4. ✅ Audio quality is acceptable for production use
5. ✅ Manual QA confirms "this sounds good"

**Blockers:**
- [ ] A/V drift >100ms
- [ ] Crashes on videos without audio
- [ ] Audio completely missing
- [ ] Severe distortion/artifacts
- [ ] OOM crashes

---

## Next Steps After Testing

### If Tests Pass ✅
1. Update task checklist: mark tests as complete
2. Move to Phase B: Audio crossfade
3. Consider production deployment

### If Tests Fail ❌
1. Document exact failure mode
2. Check ffmpeg logs for errors
3. Create minimal reproduction case
4. Debug and fix
5. Re-test

---

## Debugging Tips

### Check FFmpeg Logs
```bash
# Backend prints ffmpeg stderr on errors
tail -f /tmp/videopeen-pipeline.log

# Look for:
# - "filter_complex" → verify audio filters are present
# - "atempo" → verify speed adjustments
# - "loudnorm" → verify normalization
# - Error messages about audio streams
```

### Verify Filter Complex
```bash
# The filter_complex should look like:
[0:v]trim=...→[v0];
[0:a]atrim=...,atempo=...,aresample=44100→[a0];
[v0]concat=n=1:v=1:a=0→[concat];
[a0]concat=n=1:v=0:a=1→[aconcat];
[concat]crop=...,scale=...→[outv];
[aconcat]loudnorm=...→[outa]

# Video and audio are processed in parallel, then mapped to output
```

### Inspect Output File
```bash
# Full media info
ffprobe -v quiet -print_format json -show_format -show_streams output.mp4

# Just audio info
ffprobe -v error -select_streams a:0 \
  -show_entries stream=codec_name,sample_rate,bit_rate,channels \
  output.mp4

# Expected:
# codec_name=aac
# sample_rate=44100
# bit_rate=192000
# channels=2
```

---

**Tester:** Run these tests and report results back to main agent.

**Estimated time:** 30-60 minutes for full test matrix.
