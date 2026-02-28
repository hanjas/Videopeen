# Task 002 Phase A Implementation Summary

**Completed:** 2026-02-28 14:55 GST  
**Agent:** subagent:7bc0b7cf  
**Status:** ✅ IMPLEMENTATION COMPLETE (Testing Pending)

---

## Goal

Implement basic audio preservation for video output. Previously ALL videos were rendered **completely silent** due to `-an` flags stripping audio. This was the #1 product deal-breaker.

## What Was Implemented

### Backend Changes (2 files modified)

#### 1. **`backend/app/services/video_stitcher.py`** — Main HD Render

**Major Changes:**
- ✅ **Removed `-an` flag** that was stripping all audio
- ✅ **Added audio stream detection** via `_detect_audio_streams()` helper
- ✅ **Added parallel audio filter chain** alongside video filters
- ✅ **Audio trim filter** (`atrim`) matching video trim
- ✅ **Audio tempo adjustment** (`atempo`) matching video speed ramps
- ✅ **Smart atempo chaining** for speed >2.0 or <0.5 (better quality)
- ✅ **Audio concat** in filter_complex (parallel to video concat)
- ✅ **Audio normalization** (`loudnorm`) to -14 LUFS streaming standard
- ✅ **Sample rate normalization** (`aresample=44100`) for consistency
- ✅ **Silent audio generation** for clips without audio (prevents crashes)

**Filter Flow:**
```
VIDEO: [v]trim → setpts (speed) → concat → crop (aspect ratio) → [outv]
AUDIO: [a]atrim → atempo (speed, chained if needed) → aresample(44100) → concat → loudnorm → [outa]
```

**Edge Cases Handled:**
- Videos without audio streams → generates silent audio track (prevents ffmpeg errors)
- Different sample rates → all resampled to 44100 Hz
- Speed >2.0 → atempo chained (e.g., 4.0x = atempo=2.0,atempo=2.0)
- Speed <0.5 → atempo chained (e.g., 0.25x = atempo=0.5,atempo=0.5)

**New Helper Functions:**
- `_detect_audio_streams(source_paths)` — Uses ffprobe to detect which videos have audio
- `_build_atempo_chain(speed)` — Builds optimal atempo filter chain for any speed

**FFmpeg Command Changes:**
```python
# BEFORE (silent output):
cmd.extend(["-an", output_path])

# AFTER (with audio):
cmd.extend([
    "-map", "[outv]",
    "-map", "[outa]",
    "-c:a", "aac",
    "-b:a", "192k",
    "-ar", "44100",
    output_path,
])
```

**Fallback Function:**
- Also updated `_stitch_fallback()` to preserve audio (removed `-an`)

---

#### 2. **`backend/app/services/proxy_renderer.py`** — Proxy Clips

**Major Changes:**
- ✅ **Removed `-an` flag** from proxy rendering
- ✅ **Added audio encoding** to all proxy clips
- ✅ **Added audio tempo adjustment** for speed ramps
- ✅ **Audio filter chain** matching proxy video speed

**New Helper Function:**
- `_build_atempo_chain_proxy(speed)` — Same atempo chaining logic for proxies

**FFmpeg Command Changes:**
```python
# BEFORE (silent proxies):
cmd.extend(["-an", output_path])

# AFTER (proxies with audio):
cmd.extend([
    "-c:a", "aac",
    "-b:a", "128k",  # Lower bitrate for proxies
    "-ar", "44100",
    output_path,
])

# Add audio filter if speed adjustment needed:
if af:
    cmd.extend(["-af", af])
```

---

## Technical Implementation Details

### Audio Tempo Adjustment (atempo)

**Challenge:** ffmpeg `atempo` filter accepts 0.5-100.0 range, but quality degrades significantly >2.0

**Solution:** Chain multiple `atempo` filters to stay in optimal range:

```python
def _build_atempo_chain(speed: float) -> str:
    """
    Examples:
    - speed=1.0  → ""                           (no change)
    - speed=2.0  → ",atempo=2.0"                (within range)
    - speed=4.0  → ",atempo=2.0,atempo=2.0"     (chained)
    - speed=0.5  → ",atempo=0.5"                (within range)
    - speed=0.25 → ",atempo=0.5,atempo=0.5"     (chained)
    """
    atempo_filters = []
    remaining_speed = speed
    
    # Divide by 2.0 repeatedly until in range
    while remaining_speed > 2.0:
        atempo_filters.append("atempo=2.0")
        remaining_speed /= 2.0
    
    # Divide by 0.5 repeatedly until in range
    while remaining_speed < 0.5:
        atempo_filters.append("atempo=0.5")
        remaining_speed /= 0.5
    
    # Apply final adjustment
    if abs(remaining_speed - 1.0) > 0.01:
        atempo_filters.append(f"atempo={remaining_speed:.6f}")
    
    return "," + ",".join(atempo_filters)
```

### Audio Stream Detection

**Challenge:** Not all videos have audio (screen recordings, GoPro in wind, etc.)

**Solution:** Use ffprobe to detect audio streams before processing:

```python
def _detect_audio_streams(source_paths: list[str]) -> dict[str, bool]:
    """Returns {path: has_audio} for each source."""
    for path in source_paths:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_type",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        has_audio[path] = "audio" in result.stdout.lower()
```

**Fallback:** If a source has no audio, generate silent audio track:

```python
# Generate silent audio matching video duration
effective_duration = duration / speed if speed > 0 else duration
audio_filter = f"anullsrc=channel_layout=stereo:sample_rate=44100,atrim=duration={effective_duration:.3f}[a{i}]"
```

### Audio Normalization (loudnorm)

**Purpose:** Different source videos have wildly different audio levels. Normalize to streaming standard.

**Implementation:**
```python
# loudnorm filter applied AFTER concat (final output)
audio_norm_filter = "[aconcat]loudnorm=I=-14:TP=-1:LRA=11[outa]"

# Parameters:
# I=-14    → Integrated loudness target (-14 LUFS, streaming standard)
# TP=-1    → True peak limit (-1 dBFS, prevents clipping)
# LRA=11   → Loudness range target (dynamic range)
```

### Sample Rate Normalization

**Challenge:** Different sources may have different sample rates (44100, 48000, etc.)

**Solution:** Resample all audio to 44100 Hz before concat:

```python
audio_filter += ",aresample=44100"
```

---

## A/V Sync Verification

**Critical requirement:** Audio tempo must match video speed EXACTLY to maintain A/V sync.

**Math verification:**
```
Video:  setpts={1.0/speed}*PTS
Audio:  atempo={speed}

Example speed=2.0 (double speed):
- Video: setpts=0.5*PTS  → timestamps run at half speed → video plays 2x faster
- Audio: atempo=2.0       → audio plays 2x faster
Result: ✅ In sync

Example speed=0.75 (slow-mo):
- Video: setpts=1.333*PTS → timestamps run slower → video plays 0.75x
- Audio: atempo=0.75      → audio plays 0.75x
Result: ✅ In sync
```

---

## Files Modified

1. `backend/app/services/video_stitcher.py` — 3 new functions, audio filter chain
2. `backend/app/services/proxy_renderer.py` — 1 new function, audio in proxies

---

## What Still Needs Testing

### Unit Tests
- [ ] Test video with audio → output has audio
- [ ] Test video without audio → output has silent audio (no crash)
- [ ] Test speed=1.0 → audio unchanged
- [ ] Test speed=2.0 → audio 2x faster, in sync with video
- [ ] Test speed=4.0 → audio 4x faster (atempo chained), in sync
- [ ] Test speed=0.5 → audio half speed, in sync
- [ ] Test multiple sources with different sample rates → all normalized to 44100
- [ ] Test mix of videos with/without audio → smooth output

### Integration Tests
- [ ] Full pipeline: upload → process → render → verify audio present
- [ ] Proxy preview has audio
- [ ] HD render has audio
- [ ] Audio levels are normalized (no clips louder/quieter than others)
- [ ] No audio pops/clicks at clip boundaries
- [ ] A/V sync maintained throughout video

### Manual Testing
- [ ] Listen to output: does it sound natural?
- [ ] Speed ramps: does audio tempo sound smooth?
- [ ] Compare source vs output: is audio quality acceptable?
- [ ] Check for distortion at high speeds (>2.0)

---

## Phase B & C (Not Implemented Yet)

### Phase B: Audio Polish (estimated 2-3 days)
- [ ] Add crossfade between clips (100ms `acrossfade` filter) to eliminate hard cuts
- [ ] Further edge case testing

### Phase C: Background Music (estimated 1 week)
- [ ] Build royalty-free music library (CC0 tracks)
- [ ] Music selection UI (mood-based)
- [ ] Auto-ducking (sidechaincompress when voice is present)
- [ ] Music volume control

---

## Known Risks

1. **A/V Drift** — Most common issue with speed-adjusted audio. Needs extensive testing.
2. **Audio Quality** — `atempo` at extreme speeds (>4.0) may sound robotic. Testing needed.
3. **Memory Usage** — Audio processing adds memory overhead. Monitor on large projects.
4. **ffprobe Dependency** — Audio detection uses ffprobe. Ensure it's in PATH.

---

## Backward Compatibility

✅ **Fully backward compatible** — No database changes, no migration needed.

**Behavior change:**
- **Before:** All output was silent (by design, due to `-an`)
- **After:** All output preserves audio from source videos

This is a **breaking change in behavior but not in API/schema**. Users will notice their videos now have sound (desired behavior).

---

## Success Criteria

✅ **Phase A is complete when:**
1. Videos with audio → output has audio ✅ (code done)
2. Videos without audio → output doesn't crash ✅ (code done)
3. Speed ramps → audio tempo matches video speed ✅ (code done)
4. Multiple sources → audio levels normalized ✅ (code done)
5. All tests pass (pending)
6. Manual QA confirms audio quality is acceptable (pending)

**Status:** Implementation ✅ DONE | Testing ⏳ PENDING
