# Videopeen — Complete Product Context for Review

## What Is Videopeen?

Videopeen is an AI-powered video editor specifically built for **cooking content creators**. The target user is someone who records raw cooking footage on their phone (10-60 min single-take recordings) and wants to turn it into short-form content (60-90s) for TikTok, Instagram Reels, and YouTube Shorts.

**The market gap we identified:** ZERO cooking-specific AI video editors exist. General tools (CapCut, Opus Clip, Descript, Veed.io) don't understand cooking workflows — they don't know what a "money shot" is, can't detect recipe stages, and can't preserve the cooking narrative arc.

## Target User

- Home cooks / food bloggers who shoot raw cooking videos on phone
- They have 10-60 min of raw footage and want a polished 60-90 second clip
- They are NOT professional video editors — they don't want timeline drag-drop complexity
- They want "upload → magic → download" with ability to tweak via natural language
- Mobile-first mindset (shoot on phone, edit on couch)

## Current Product State (What We Have Today)

### The User Journey (Actual Flow)

1. **Sign in** — Google SSO via NextAuth
2. **Create project** — Give it a name, optional dish name and recipe steps
3. **Upload videos** — Drag-drop multiple video files (any format: MOV, MP4, etc.)
4. **Click "Generate"** — AI pipeline starts:
   - Extracts frames (1 per 2 seconds) from all videos
   - Claude Vision analyzes frames in batches, detects cooking **actions** (chop onions, sear meat, plate dish, etc.)
   - Claude acts as an editor — selects best clips, orders them in cooking narrative arc, applies speed ramps
   - Pre-renders proxy clips at 480p for instant preview
   - Renders full HD final video
5. **Watch preview** — Auto-plays the AI-generated edit
6. **Conversational editing** — Type natural language instructions:
   - "Remove the banana shots"
   - "Make it faster"
   - "Add more plating shots"
   - Claude re-edits, new proxy preview appears in ~16 seconds
7. **Undo/Redo** — Timeline version snapshots, can go back/forward
8. **Export/Download** — HD rendered final video

### Tech Stack

- **Frontend:** Next.js 14, TypeScript, Tailwind CSS, dark theme (#0a0a0a + orange accent #f97316)
- **Backend:** Python FastAPI, MongoDB (via Docker), ffmpeg for all video processing
- **AI:** Claude Sonnet 4.5 (Anthropic API) for both vision analysis and editing decisions
- **Auth:** Google SSO via NextAuth.js
- **Real-time:** WebSocket for live progress updates during pipeline
- **Video encoding:** Apple VideoToolbox hardware acceleration (h264_videotoolbox)

### Architecture — The Pipeline (V6, Action-Based)

This is the core innovation. We treat cooking as a sequence of **actions** detected from temporal frame flow.

```
Upload videos
    ↓
1. Dense Frame Extraction (ffmpeg, 1 frame every 2 seconds, 768px)
   - 10 min video → ~300 frames as JPEGs on disk
    ↓
2. Action Detection (Claude Vision, batches of 15 frames)
   - Each batch: 15 frames sent as base64 images to Claude
   - Claude identifies: action description, start/end timestamps, recipe step, visual quality score, action type
   - 5 concurrent API calls for speed
   - Example actions detected: "dicing onions", "searing chicken breast", "plating with microgreens"
    ↓
3. Edit Plan (Claude as Editor, 1 API call)
   - Receives: all detected actions + recipe context + target duration
   - Returns: ordered clip list with start/end times, speed factors, descriptions, reasons
   - Applies speed ramps: 2x for boring parts (stirring), 0.5x for hero moments (cheese pull)
   - Maintains cooking narrative arc: prep → cook → transform → plate → hero shot
    ↓
4. Proxy Pre-render (ffmpeg, 480p, 3 concurrent)
   - Every detected action gets a 480p proxy clip rendered
   - Both timeline clips AND clip pool (unused actions) get proxied
   - This enables instant re-editing without re-rendering
    ↓
5. Fast Concat (ffmpeg concat demuxer, NO re-encoding)
   - Timeline clips concatenated in 0.07 seconds
   - This is the "proxy preview" user sees immediately
    ↓
6. HD Render (ffmpeg filter_complex, VideoToolbox, 12Mbps)
   - Full quality render with speed ramps
   - Runs in background — user already has proxy preview to watch
```

### Conversational Editing (How It Works)

When user types "Remove banana shots":
1. Current timeline clips + clip pool + user instruction sent to Claude
2. Claude returns new clip selection (tool_use response)
3. Backend updates timeline, bumps version, saves snapshot for undo
4. Fast proxy concat → new preview in ~16 seconds
5. Background HD re-render starts automatically

### Features We Have

| Feature | Status | How It Works |
|---------|--------|--------------|
| Multi-video upload | ✅ | Chunked upload (1MB), any video format |
| AI action detection | ✅ | Claude Vision, 15-frame batches, 5 concurrent |
| AI edit plan generation | ✅ | Claude as editor, cooking narrative arc |
| Speed ramps | ✅ | 2x boring, 0.5x hero moments, per-clip |
| Instant proxy preview | ✅ | Pre-rendered 480p clips, concat in 0.07s |
| Conversational editing | ✅ | Natural language → Claude re-edits → new preview |
| Undo/Redo | ✅ | Timeline version snapshots in MongoDB |
| HD render | ✅ | VideoToolbox h264, 12Mbps, background render |
| Real-time progress | ✅ | WebSocket updates during pipeline |
| Google SSO | ✅ | NextAuth.js |
| BYOK API keys | ✅ | Users can use their own Anthropic API key |
| Dark theme | ✅ | #0a0a0a background, orange accent |
| Clip pool | ✅ | Unused actions available for manual inclusion |
| Recipe context | ✅ | Optional dish name + recipe steps improve AI decisions |
| Auto-project naming | ✅ | AI generates project name |
| User isolation | ✅ | Projects scoped by user email |

### Features We DON'T Have Yet

| Feature | Notes |
|---------|-------|
| Audio/music | No audio processing at all — videos are silent |
| Captions/subtitles | No text overlays |
| Transitions | Hard cuts only — no fades, wipes, etc. |
| Text overlays | No titles, lower thirds, etc. |
| Filters/color grading | No visual effects |
| Multi-format export | Only 16:9 — no 9:16 (vertical), no 1:1 (square) |
| Thumbnail generation | No custom thumbnail for social media |
| Templates/styles | No preset editing styles |
| Collaboration | Single user only |
| Mobile app | Web only, not optimized for mobile |
| Voice commands | Text only for editing |
| Music/sound library | No stock audio |
| Brand kit | No logos, watermarks, custom fonts |
| Analytics/insights | No video performance tracking |
| Social media publishing | No direct posting to TikTok/YouTube/Instagram |
| Batch processing | One project at a time |
| AI voiceover | No generated narration |
| Smart cropping | No auto-reframe for different aspect ratios |
| Scene transitions | No animated transitions between clips |
| B-roll suggestions | No stock footage integration |
| Highlight detection | Only cooking-specific, not general |
| Multi-language | English only |

### Performance (Actual Benchmarks — Feb 28, 2026)

Test: 3 cooking videos, 11.9 minutes total footage (711.5 seconds), 356 frames extracted

| Step | Time | % of Total |
|------|------|------------|
| Frame extraction (356 frames) | 49s | 17% |
| Action detection (25 batches → 103 actions) | 1m 13s | 25% |
| Edit plan (→ 18 clips) | 38s | 13% |
| Proxy pre-render (102 clips) | 50s | 17% |
| Proxy concat (18 clips) | 0.07s | ~0% |
| HD render (18 clips) | 1m 22s | 28% |
| **Total pipeline** | **~4m 53s** | 100% |

Conversational edit: **~16 seconds** to new preview (Claude call + proxy concat)

### Known Issues

1. **OOM on 18GB RAM** — Running frontend + backend + pipeline simultaneously can crash
2. **No audio** — All output videos are silent
3. **Portrait video metadata** — Source videos have rotation=-90, ffmpeg handles it but occasional issues
4. **No mobile optimization** — UI is desktop-first
5. **No error recovery** — Pipeline failure = start over
6. **No progress for upload** — User doesn't see upload percentage
7. **One clip had 0 duration** — Edge case in action detection

### Business Model (Planned)

- **Free tier:** BYOK (bring your own API key) — user pays Anthropic directly
- **Pro tier:** $25/month — hosted API credits included
- **Infrastructure cost:** ~$5-10/month (Vercel + Railway + MongoDB Atlas + Cloudflare R2 + Modal.com for GPU)

### Deployment Plan (Not Yet Done)

Currently local-only. Plan:
- Vercel (frontend)
- Railway (backend)
- MongoDB Atlas (free tier)
- Cloudflare R2 (video storage)
- Modal.com (GPU processing for ffmpeg)

---

## What We Want From You

You are reviewing this as a **product expert and power user** who deeply understands what modern, intelligent video editing should feel like. Think from the perspective of:

1. A cooking content creator who posts daily on TikTok/Reels
2. A product designer who's used every video editing tool out there (CapCut, Descript, Opus Clip, Runway, Veed.io, InVideo, Kapwing)
3. Someone who understands the latest AI capabilities and modern UX patterns

We want:
1. **Honest review** of the current product — what's good, what's missing, what feels broken from a user perspective
2. **Feature gap analysis** — what would make this a 10/10 product vs the current ~10% we estimate
3. **Priority ranking** — what to build next for maximum user impact
4. **UX critique** — does the flow make sense? What's confusing?
5. **Competitive analysis** — how does this compare to existing tools? What's our unique edge?
6. **Moonshot ideas** — features that would make this truly revolutionary, not just "another AI editor"
7. **Monetization feedback** — is the pricing model right?

Be brutally honest. We'd rather hear hard truths than polite encouragement.
