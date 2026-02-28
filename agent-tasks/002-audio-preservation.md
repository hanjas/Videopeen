# Task 002: Audio Preservation + Sync

**Priority:** 🔴 CRITICAL
**Effort:** 2 weeks
**Status:** ⬜ NOT STARTED
**Depends on:** Nothing (can run parallel with 001)
**Assigned to:** —

---

## Goal

Preserve original audio from source videos in the final output. Currently ALL output is silent (-an flag strips audio). This is the #1 deal-breaker.

## Why This Matters

- Silent video = DOA for social media
- Cooking content NEEDS sizzle sounds, knife chops, voice narration
- Without audio, product is a "demo, not a product" (agent review)

## Complexity Warning ⚠️

Audio + speed ramps is TRICKY:
- 2x video speed → audio must also be 2x (atempo filter, max 2.0 per chain)
- Speed ramp transitions can cause audio pops/clicks
- Multiple clips from different sources = different audio levels
- Portrait videos may have mono vs stereo mismatch

## What To Change

### Phase A: Basic Audio Preservation (Days 1-5)

#### 1. `backend/app/services/video_stitcher.py`

**Current:** `-an` flag strips all audio
**Change:** Include audio stream, apply tempo changes matching video speed

```python
# Current filter (video only):
trim_filter = f"[{src_idx}:v]trim=start={start}:end={end},setpts=PTS-STARTPTS"

# New filter (video + audio):
video_filter = f"[{src_idx}:v]trim=start={start}:end={end},setpts=PTS-STARTPTS"
audio_filter = f"[{src_idx}:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS"

# With speed ramp:
if speed != 1.0:
    video_filter += f",setpts={1.0/speed}*PTS"
    # atempo only accepts 0.5-2.0, chain for larger values
    audio_filter += f",atempo={speed}"  # Simple case
```

**Key ffmpeg atempo rules:**
- atempo range: 0.5 to 100.0 (but quality degrades >2.0)
- For speed=2.0: `atempo=2.0`
- For speed=4.0: `atempo=2.0,atempo=2.0` (chain)
- For speed=0.5: `atempo=0.5`
- For speed=0.25: `atempo=0.5,atempo=0.5` (chain)

#### 2. Remove `-an` flags everywhere

Files to update:
- `video_stitcher.py` — main render
- `proxy_renderer.py` — proxy clips (keep audio in proxies too!)
- `render.py` — HD render

#### 3. Audio normalization

Different source videos have different audio levels. Normalize to -14 LUFS (streaming standard):

```python
# Add loudnorm filter to final output
"-af", "loudnorm=I=-14:TP=-1:LRA=11"
```

### Phase B: Speed Ramp Audio Sync (Days 6-9)

#### 4. Handle edge cases

- Source video with no audio track → don't crash, skip audio
- Speed factor exactly 1.0 → no atempo needed
- Speed factor 0 or negative → sanitize input
- Different audio sample rates between clips → resample to 44100

#### 5. Crossfade between clips

Hard audio cuts between clips sound jarring. Add short crossfade:

```python
# acrossfade=d=0.1:c1=tri:c2=tri (100ms triangular crossfade)
```

### Phase C: Background Music (Days 10-14)

#### 6. Royalty-free music library

- Create `backend/music/` directory with 10-15 tracks
- Categories: cozy, upbeat, cinematic, minimal
- Sources: Pixabay, Free Music Archive (CC0 licensed)
- Store metadata: `music/library.json` with mood tags

#### 7. Auto-ducking (music quieter when voice detected)

```python
# ffmpeg sidechaincompress: duck music when source audio is loud
# [source_audio][music]sidechaincompress=threshold=0.02:ratio=6:attack=200:release=1000
```

#### 8. Music selection UI

- Frontend: dropdown to pick music mood or "No music"
- Backend: mix music track with source audio
- Volume control: music at -20dB under source audio

---

## Checklist

### Phase A: Basic Audio
- [x] Remove `-an` from video_stitcher.py
- [x] Add audio trim filter matching video trim
- [x] Add atempo filter matching speed ramps
- [x] Handle atempo chaining for speed >2.0 or <0.5
- [x] Audio normalization (loudnorm)
- [x] Handle videos without audio track (no crash)
- [x] Handle different sample rates between sources (aresample=44100)
- [x] Remove `-an` from proxy_renderer.py
- [ ] Test: basic video with audio → output has sound
- [ ] Test: speed ramp 2x → audio plays at 2x correctly

### Phase B: Edge Cases + Polish
- [x] Handle videos without audio track (no crash) — DONE IN PHASE A
- [x] Handle different sample rates between sources — DONE IN PHASE A
- [ ] Add audio crossfade between clips (100ms)
- [x] Remove `-an` from proxy_renderer.py — DONE IN PHASE A
- [ ] Test: multiple source videos → smooth audio transitions

### Phase C: Background Music
- [ ] Create music/ directory with 10-15 CC0 tracks
- [ ] Create music/library.json with mood tags
- [ ] Backend: mix music with source audio
- [ ] Backend: auto-ducking (sidechaincompress)
- [ ] Frontend: music selector UI (mood dropdown)
- [ ] Frontend: volume control slider
- [ ] Test: video with background music sounds good

## Technical Notes

- ffmpeg `atempo` filter is audio-only (video uses `setpts`)
- `atempo` and `setpts` must stay in sync or A/V drift occurs
- Test with short clips first (5-10 sec) before full pipeline
- VideoToolbox encoding supports audio passthrough

## Risks

- **A/V sync drift** — Most common issue with speed ramps. Test extensively.
- **Audio pops at clip boundaries** — Crossfade should fix, but test.
- **OOM with audio processing** — Audio adds memory load. Monitor.
- **Music licensing** — ONLY use CC0/royalty-free. No Epidemic Sound etc.
