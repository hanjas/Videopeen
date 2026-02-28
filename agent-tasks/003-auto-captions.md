# Task 003: Auto-Captions (Whisper + Burn-in)

**Priority:** 🔴 CRITICAL
**Effort:** 1 week
**Status:** ⬜ NOT STARTED
**Depends on:** Task 002 (Audio Preservation) — need audio to transcribe!
**Assigned to:** —

---

## Goal

Auto-generate captions from video audio using Whisper, then burn them into the video. 85% of social media video is watched muted — captions are table stakes.

## Why This Matters

- Muted autoplay is default on TikTok/IG/YouTube
- Captions = 30-50% higher engagement (industry data)
- Cooking content needs text for ingredients/quantities ("2 cloves garlic")
- Every competitor has this

## What To Change

### 1. Install Whisper

Option A: **OpenAI Whisper API** (cloud, fast, costs ~$0.006/min)
Option B: **whisper.cpp** (local, free, slower on CPU)
Option C: **faster-whisper** (local, Python, good balance)

**Recommended: faster-whisper** — runs locally, no API cost, good speed on M-series Mac.

```bash
pip install faster-whisper
```

### 2. New service: `backend/app/services/captioner.py`

```python
async def generate_captions(video_path: str, output_srt: str) -> str:
    """
    Extract audio → transcribe with Whisper → save as SRT file.
    Returns path to SRT file.
    """
    # Step 1: Extract audio from video
    # ffmpeg -i video.mp4 -vn -acodec pcm_s16le -ar 16000 -ac 1 audio.wav
    
    # Step 2: Transcribe with faster-whisper
    # model = WhisperModel("base", device="cpu", compute_type="int8")
    # segments, info = model.transcribe(audio_path, word_timestamps=True)
    
    # Step 3: Generate SRT from segments
    # Each segment has: start, end, text
    
    # Step 4: Return SRT path
```

### 3. Burn captions into video

Two approaches:
- **Hard burn (drawtext):** Captions baked into pixels. Works everywhere.
- **Soft subs (mov_text):** Separate track. Player can toggle. Not all platforms support.

**Go with hard burn** — guaranteed to work on TikTok/IG/YouTube.

```bash
# ffmpeg burn-in with styling
ffmpeg -i video.mp4 -vf "subtitles=captions.srt:force_style='FontSize=24,FontName=Arial Bold,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,Outline=2,Alignment=2,MarginV=40'" output.mp4
```

**Caption style for cooking content:**
- Font: Bold sans-serif (Arial Bold or Montserrat Bold)
- Color: White with black outline (readable on any background)
- Position: Bottom center, above safe zone (MarginV=40)
- Size: Large enough for mobile viewing (24-28)
- Background: Optional semi-transparent box for extra readability

### 4. Pipeline integration

Add to `pipeline.py` AFTER HD render:
```python
# Optional: generate captions
if project.get("enable_captions", True):
    srt_path = await captioner.generate_captions(output_path, srt_output_path)
    captioned_path = await burn_captions(output_path, srt_path, captioned_output_path)
```

### 5. Frontend: Caption toggle

- Checkbox: "Auto-generate captions" (default ON)
- Caption style selector: "Bold White" | "Subtitle Bar" | "Minimal"
- Preview captions in proxy video

### 6. Caption editing

- After generation, show transcript in sidebar
- User can edit text (fix Whisper errors)
- Re-burn with corrected text

---

## Checklist

- [ ] Install faster-whisper in backend venv
- [ ] Create `backend/app/services/captioner.py`
- [ ] Audio extraction from final video (ffmpeg → wav)
- [ ] Whisper transcription → SRT file generation
- [ ] SRT burn-in via ffmpeg subtitles filter
- [ ] Caption styling (white bold, black outline)
- [ ] Pipeline integration (auto-caption after render)
- [ ] Frontend: caption toggle checkbox
- [ ] Frontend: caption style selector (3 presets)
- [ ] Frontend: transcript display + edit
- [ ] Test: video with clear speech → accurate captions
- [ ] Test: video with no speech → empty captions (no crash)
- [ ] Test: caption positioning on 16:9, 9:16, 1:1

## Technical Notes

- faster-whisper "base" model = ~150MB, good accuracy for English
- Transcription time: ~10-30 sec for 60-90 sec video (on M-series Mac)
- SRT format is simple: index, timecode, text. Easy to generate.
- For 9:16 vertical, captions should be larger font (phone screen is narrow)
- Word-level timestamps available for karaoke-style highlighting (future feature)

## Risks

- **Whisper accuracy** — Cooking sounds (sizzling, clanking) can confuse speech detection. May need speech activity detection (VAD) first.
- **Non-English content** — Whisper supports 99 languages but accuracy varies
- **No speech videos** — Some cooking videos have no narration, just ASMR sounds. Captions would be empty → handle gracefully.
