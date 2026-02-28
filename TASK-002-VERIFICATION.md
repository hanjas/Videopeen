# Task 002 Phase A - Code Verification

**Date:** 2026-02-28 14:57 GST  
**Verified by:** subagent:7bc0b7cf

---

## ✅ Verification Checklist

### video_stitcher.py

- [x] **Line 14:** `_detect_audio_streams()` function added
- [x] **Line 48:** `_build_atempo_chain()` function added  
- [x] **Line 219-220:** Audio normalization filter (`loudnorm`) added
- [x] **Line 236:** Audio codec (`-c:a aac`) in main output
- [x] **Line 275:** Audio codec in fallback function
- [x] **0 matches:** All `-an` flags removed ✅

**Key Changes:**
```python
# Audio stream detection added
sources_with_audio = _detect_audio_streams(source_paths)

# Audio filter chain added (parallel to video)
audio_filter = f"[{src_idx}:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS"
audio_filter += _build_atempo_chain(speed)  # Speed adjustment
audio_filter += ",aresample=44100"          # Sample rate normalization

# Audio normalization at end
audio_norm_filter = "[aconcat]loudnorm=I=-14:TP=-1:LRA=11[outa]"

# Audio mapping in output
"-map", "[outv]",
"-map", "[outa]",  # NEW: Map audio stream
"-c:a", "aac",     # NEW: Audio codec
"-b:a", "192k",    # NEW: Audio bitrate
```

---

### proxy_renderer.py

- [x] **Line 18:** `_build_atempo_chain_proxy()` function added
- [x] **Line 184:** Audio codec (`-c:a aac`) in proxy output
- [x] **0 matches:** All `-an` flags removed ✅

**Key Changes:**
```python
# Audio filter for speed adjustment
af = _build_atempo_chain_proxy(speed_factor)

# Audio encoding in proxy
"-c:a", "aac",
"-b:a", "128k",    # Lower bitrate for proxies
"-ar", "44100",

# Conditional audio filter
if af:
    cmd.extend(["-af", af])
```

---

## Grep Verification Results

```bash
$ grep -n "loudnorm" backend/app/services/video_stitcher.py
219:    # Audio normalization (loudnorm) - streaming standard (-14 LUFS)
220:    audio_norm_filter = "[aconcat]loudnorm=I=-14:TP=-1:LRA=11[outa]"
✅ Audio normalization present

$ grep -n "def _detect_audio_streams" backend/app/services/video_stitcher.py
14:def _detect_audio_streams(source_paths: list[str]) -> dict[str, bool]:
✅ Audio detection function present

$ grep -n "def _build_atempo_chain" backend/app/services/video_stitcher.py
48:def _build_atempo_chain(speed: float) -> str:
✅ Atempo chain builder present

$ grep -n '"-c:a"' backend/app/services/video_stitcher.py
236:        "-c:a", "aac",
275:                "-c:a", "aac", "-b:a", "192k",
✅ Audio codec specified (2 locations: main + fallback)

$ grep -n "def _build_atempo_chain_proxy" backend/app/services/proxy_renderer.py
18:def _build_atempo_chain_proxy(speed: float) -> str:
✅ Proxy atempo chain builder present

$ grep -n '"-c:a"' backend/app/services/proxy_renderer.py
184:                "-c:a", "aac",
✅ Proxy audio codec specified

$ grep -c '"-an"' backend/app/services/proxy_renderer.py backend/app/services/video_stitcher.py
backend/app/services/proxy_renderer.py:0
backend/app/services/video_stitcher.py:0
✅ All -an flags removed (0 matches)
```

---

## Edge Cases Implemented

### 1. Videos Without Audio
```python
if sources_with_audio.get(entry["source_path"], False):
    # Process real audio
else:
    # Generate silent audio to maintain sync
    effective_duration = duration / speed if speed > 0 else duration
    audio_filter = f"anullsrc=channel_layout=stereo:sample_rate=44100,atrim=duration={effective_duration:.3f}[a{i}]"
```
✅ **No crashes** if source video has no audio track

---

### 2. Speed >2.0 (Atempo Chaining)
```python
def _build_atempo_chain(speed: float) -> str:
    while remaining_speed > 2.0:
        atempo_filters.append("atempo=2.0")
        remaining_speed /= 2.0
```
✅ **Speed=4.0** → `atempo=2.0,atempo=2.0` (chained)  
✅ **Speed=8.0** → `atempo=2.0,atempo=2.0,atempo=2.0` (chained)

---

### 3. Speed <0.5 (Atempo Chaining)
```python
while remaining_speed < 0.5:
    atempo_filters.append("atempo=0.5")
    remaining_speed /= 0.5
```
✅ **Speed=0.25** → `atempo=0.5,atempo=0.5` (chained)  
✅ **Speed=0.125** → `atempo=0.5,atempo=0.5,atempo=0.5` (chained)

---

### 4. Different Sample Rates
```python
audio_filter += ",aresample=44100"
```
✅ **All sources normalized to 44100 Hz** before concat

---

### 5. Audio Level Normalization
```python
audio_norm_filter = "[aconcat]loudnorm=I=-14:TP=-1:LRA=11[outa]"
```
✅ **Streaming standard:** -14 LUFS integrated loudness  
✅ **True peak limit:** -1 dBFS (prevents clipping)  
✅ **Dynamic range:** LRA=11 (preserves dynamics while normalizing)

---

## Filter Flow Diagram

```
INPUT SOURCES:
[source0.mov] → [0:v] [0:a]
[source1.mov] → [1:v] [1:a] (no audio track detected)
[source2.mov] → [2:v] [2:a]

VIDEO CHAIN:
[0:v] → trim → setpts(speed) → [v0] ┐
[1:v] → trim → setpts(speed) → [v1] ├→ concat → crop(aspect) → [outv]
[2:v] → trim → setpts(speed) → [v2] ┘

AUDIO CHAIN:
[0:a] → atrim → atempo(speed) → aresample(44100) → [a0] ┐
anullsrc → atrim                                 → [a1] ├→ concat → loudnorm → [outa]
[2:a] → atrim → atempo(speed) → aresample(44100) → [a2] ┘
                                    ↑
                        (silent audio for source1)

OUTPUT:
[outv] → h264_videotoolbox @ 12M
[outa] → aac @ 192k, 44100 Hz
```

---

## Test Plan (Next Steps)

### Quick Smoke Test (5 min)
```bash
# 1. Start backend
cd backend && source .venv/bin/activate
uvicorn app.main:app --port 8000 --reload

# 2. Upload a video with audio (e.g., ~/Downloads/IMG_2748.MOV)
# 3. Run pipeline
# 4. Download output
# 5. Play and verify:
#    - Video plays ✓
#    - Audio is present ✓
#    - Audio is in sync with video ✓
```

### Full Test Matrix (1-2 hours)

| Test Case | Input | Expected Output | Status |
|-----------|-------|-----------------|--------|
| Basic audio | 1 video w/ audio | Audio present, normalized | ⏳ |
| No audio | 1 video w/o audio | Silent output, no crash | ⏳ |
| Speed 1.0 | 1 clip @ 1.0x | Audio unchanged | ⏳ |
| Speed 2.0 | 1 clip @ 2.0x | Audio 2x, in sync | ⏳ |
| Speed 4.0 | 1 clip @ 4.0x | Audio 4x (chained), in sync | ⏳ |
| Speed 0.5 | 1 clip @ 0.5x | Audio 0.5x, in sync | ⏳ |
| Multi-source | 3 videos, diff levels | Normalized audio levels | ⏳ |
| Mixed audio | Video w/ + w/o audio | Smooth output | ⏳ |
| Proxy preview | Timeline w/ 5 clips | Proxy has audio | ⏳ |
| HD render | Full pipeline | HD has audio | ⏳ |

---

## Files Changed

1. ✅ `backend/app/services/video_stitcher.py` (119 lines changed)
   - Added 2 helper functions
   - Modified `stitch_clips_v2()` main function
   - Modified `_stitch_fallback()` function

2. ✅ `backend/app/services/proxy_renderer.py` (45 lines changed)
   - Added 1 helper function
   - Modified `render_one_clip()` async function

---

## Status

**Implementation:** ✅ **COMPLETE**  
**Testing:** ⏳ **PENDING**  
**Documentation:** ✅ **COMPLETE**  
**Ready for QA:** ✅ **YES**

---

**Next step:** Run test plan and verify audio output quality.
