# Videopeen — AI Cooking Video Editor

## What Is This?

Videopeen is an AI-powered video editor specifically for cooking content creators. You upload raw cooking footage (typically 10-40 min single-take phone recordings), and the AI analyzes, selects the best moments, arranges them into a coherent cooking story, and renders a short-form video (60-90s for TikTok/Reels/Shorts).

**The key insight:** ZERO cooking-specific AI video editors exist. General tools (CapCut, Opus Clip, Descript) don't understand cooking workflows — they don't know what a "money shot" is, can't detect recipe stages, and can't preserve the cooking narrative arc.

## Tech Stack

### Backend
- **Framework:** FastAPI (Python 3.11)
- **AI:** Claude Sonnet 4.5 via Anthropic API (OAuth token)
- **Database:** MongoDB (Docker container `videopeen-mongo`, localhost:27017, db `videopeen`)
- **Video processing:** ffmpeg (frame extraction + video stitching)
- **Location:** `videopeen/backend/`
- **Venv:** `videopeen/backend/.venv/`
- **Start:** `cd backend && source .venv/bin/activate && python -m uvicorn app.main:app --port 8000 --reload`

### Frontend
- **Framework:** Next.js 14 + TypeScript + Tailwind CSS
- **Auth:** NextAuth.js with Google SSO
- **Theme:** Dark (#0a0a0a) + orange accent (#f97316)
- **Location:** `videopeen/frontend/`
- **Start:** `cd frontend && npm run dev` (port 3000)

### API Authentication (IMPORTANT)
- Uses OAuth token (`sk-ant-oat...`) stored in `backend/.env` as `ANTHROPIC_API_KEY`
- **Required headers for every Claude API call:**
  ```
  anthropic-beta: claude-code-20250219,oauth-2025-04-20
  user-agent: claude-cli/1.0.0 (external, cli)
  x-app: cli
  ```
- Model: `claude-sonnet-4-5` (env: `VISION_MODEL` and `TEXT_MODEL`)
- BYOK: Users can save their own API key in settings, backend uses it if available

### Infrastructure (SaaS Plan — Not Yet Deployed)
- Vercel (frontend) + Railway (backend) + MongoDB Atlas (free) + Cloudflare R2 (storage) + Modal.com (GPU processing)
- Total: ~$5-10/mo
- Business model: Free tier (BYOK) + Pro $25/mo (hosted credits)

## The Pipeline (V6 — Action-Based)

This is the core innovation. Previous versions (V1-V5) tried scene detection, per-frame analysis, etc. V6 treats cooking as a sequence of **actions** detected from temporal frame flow.

### Flow
```
Upload videos
    ↓
1. Dense Frame Extraction (1 frame every 2 seconds via ffmpeg)
    ↓
2. Action Detection (Claude Vision, batches of 10 frames)
   - Detects: what action is happening, recipe step, visual quality, action type
   - Understands temporal flow (frame N follows frame N-1)
    ↓
3. Edit Plan (Claude as Editor)
   - Gets all detected actions + recipe context
   - Selects best clips, orders them in cooking narrative arc
   - Applies speed factors (2x for boring parts, 0.5x for money shots)
   - Respects target duration
    ↓
4. Auto-Render (ffmpeg stitching with speed ramps)
    ↓
5. Preview + Conversational Editing
   - User sees assembled video, can request changes via text
   - "Remove the chopping part" / "Make it 30 seconds" / "More plating shots"
   - Claude re-edits based on instruction
```

### Key Design Decisions
- **Dense frames, NOT scene detection** — PySceneDetect is useless for single-take cooking videos (no hard cuts)
- **Batch processing** — 10 frames per Claude Vision call (cost + speed optimization)
- **Actions as fundamental units** — Not "scenes" or "segments", but cooking ACTIONS (dice onions, sear chicken, plate with garnish)
- **Speed ramps** — Boring parts get 2x speed, hero moments get normal/slow speed
- **Concurrency: 2** (was 3, reduced to prevent OOM on 18GB RAM)
- **Claude-only** — No Gemini, no other models
- **Visual-only** — No audio processing (yet)

## UX Philosophy (V2 Redesign — Feb 22, 2026)

Based on 10 expert reviews. See `docs/UX-REDESIGN-V2.md` for full synthesis.

### Core Principle
**AI is the editor. User is the director.** Users should never manually drag-drop 18 clips. They watch the AI's cut, and if they want changes, they describe them in natural language.

### Flow (3 clicks to export)
```
Upload → AI Processes → Video auto-plays → Export
                              ↓ (optional)
                        Text: "Make it faster"
                              ↓
                        Claude re-edits → New preview
```

### Key UX Rules
- **Preview first** — Show assembled video, not clip cards
- **Conversational editing** — Text input (future: voice), not drag-drop
- **3 pages only** — Landing, Dashboard, Editor
- **Auto-save, auto-name** — Zero friction
- **"Advanced Edit" as escape hatch** — Old review page still accessible for power users
- **Mobile-first** — Designed for one-handed couch editing

## Project Structure

```
videopeen/
├── backend/
│   ├── .env                    # API keys, MongoDB URI
│   ├── .venv/                  # Python virtual environment
│   ├── app/
│   │   ├── main.py             # FastAPI app, routers, CORS, static files
│   │   ├── config.py           # Settings (dirs, env vars)
│   │   ├── models/
│   │   │   └── project.py      # Pydantic models, ProjectStatus enum
│   │   ├── routers/
│   │   │   ├── projects.py     # CRUD + process trigger (user-isolated via x-user-email)
│   │   │   ├── upload.py       # File upload handling
│   │   │   ├── process.py      # Processing trigger
│   │   │   ├── edit_plan.py    # Edit plan CRUD, confirm, render, thumbnails, refine
│   │   │   └── user_settings.py # BYOK API key storage
│   │   ├── services/
│   │   │   ├── pipeline.py     # V6 orchestrator (frames → actions → edit → render)
│   │   │   ├── video_analyzer.py # Claude Vision calls (action detection + edit planning)
│   │   │   ├── video_processor.py # ffmpeg frame extraction
│   │   │   ├── video_stitcher.py  # ffmpeg clip stitching with speed ramps
│   │   │   ├── render.py       # Post-confirmation render service
│   │   │   └── clip_selector.py   # Legacy (V5 and earlier)
│   │   └── websocket/
│   │       └── manager.py      # WebSocket for live progress updates
│   └── requirements.txt
├── frontend/
│   ├── .env.local              # Google OAuth creds, NextAuth config
│   ├── app/
│   │   ├── page.tsx            # Landing page
│   │   ├── layout.tsx          # Root layout
│   │   ├── api/auth/[...nextauth]/route.ts  # NextAuth Google SSO
│   │   └── dashboard/
│   │       ├── layout.tsx      # Dashboard shell (sidebar, auth sync, toast)
│   │       ├── page.tsx        # Project list / dashboard
│   │       ├── new/page.tsx    # New project form
│   │       ├── settings/page.tsx # User settings (API key, profile)
│   │       └── project/[id]/
│   │           ├── page.tsx    # Editor (video preview + conversational edit)
│   │           └── review/page.tsx # Advanced edit (drag-drop clips) — escape hatch
│   ├── components/
│   │   ├── Sidebar.tsx         # Navigation sidebar
│   │   └── Toast.tsx           # Global toast notifications
│   └── lib/
│       └── api.ts              # API client (fetch wrapper, types, WebSocket)
├── docs/
│   ├── UX-REDESIGN-V2.md      # Expert synthesis doc
│   ├── PREVIEW-BEFORE-RENDER.md # Original preview blueprint
│   └── research/
│       └── agent-brainstorm-all.md # 25 research agent responses
└── PROJECT.md                  # ← This file
```

## MongoDB Collections

- **projects** — Project metadata (name, status, progress, output_path, user_email)
- **video_clips** — Uploaded video file records (path, duration)
- **video_analyses** — Detected actions (action_id, timestamps, description, quality scores)
- **edit_decisions** — Selected clips for stitching (backward compat)
- **edit_plans** — Full edit plan with timeline.clips[], clip_pool[], history[], editor_notes
- **user_settings** — BYOK API keys per user

## Status Enum
```
CREATED → UPLOADING → PROCESSING → ANALYZING → SELECTING → STITCHING → COMPLETED
                                                                  ↗
                                                             (ERROR at any point)
```
Note: REVIEW status still exists in code but pipeline now auto-renders (V2 redesign).

## Key Bugs Fixed

1. **JSON parsing** (Feb 22) — Claude API responses sometimes include extra text/multiple JSON objects. Fixed with `_extract_json()` and `_extract_batch_json()` helpers using balanced-brace matching instead of greedy regex.

2. **OOM SIGKILL** — Frontend + backend + pipeline together crashes on 18GB RAM. Solution: close frontend during pipeline runs, or reduce concurrency to 2.

3. **Source videos are portrait** — 1920x1080 with rotation=-90 metadata. ffmpeg handles this correctly.

4. **Duration overshoot** — Editor system prompt rewritten with CRITICAL DURATION RULE to stay within target.

## Performance Benchmarks

| Video | Actions | Clips | Duration | Pipeline Time | API Calls |
|-------|---------|-------|----------|--------------|-----------|
| Loaded Fries (5 vids) | ~40 | 20 | 97.3s | ~16 min | ~63 |
| Bread Toast (3 vids) | ~30 | 18 | 91.3s | ~15 min | ~60 |

V6 is 2x faster than V5 (16 min vs 33 min) and 4x fewer API calls (63 vs 247).

## Backups

- `videopeen-backup-2026-02-21/` — Pre-V3
- `videopeen-backup-2026-02-21-v2/` — Pre-V3 (second)
- `videopeen-backup-2026-02-22-v5/` — Pre-action-based (V5)

## What's Done

- [x] V6 action-based pipeline (working, tested)
- [x] Frontend: Next.js 14, dark theme, Google SSO
- [x] Backend API: CRUD, upload, process, WebSocket progress, user isolation
- [x] BYOK API key management
- [x] Edit plan system (timeline + clip pool + versioning)
- [x] V2 UX: Preview-first flow (pipeline auto-renders, no REVIEW stop)
- [x] V2 UX: Conversational editing (text instruction → Claude re-edits)
- [x] Proxy/LEGO system (clip pre-rendering + fast concat)
- [x] Undo/redo (timeline snapshots)
- [x] Auto-name projects
- [x] New Project → Dashboard modal
- [x] Settings → Slide-out drawer
- [x] Speed: 768px frames, 5 concurrent API, batch 15, VideoToolbox encoding

## What's Next

1. [ ] Test speed optimizations with fresh upload (changes applied, not yet benchmarked)
2. [ ] Test conversational editing end-to-end (source_path fix applied)
3. [ ] Smart frame selection (CV-based dedup — 60-70% frame reduction)
4. [ ] Streaming pipeline (parallel video processing)
5. [ ] Progressive delivery (show rough edit in 30 sec)
6. [ ] Cooking stages grouping + AI confidence scores
7. [ ] Auto-captions (critical for TikTok/Reels)
8. [ ] Multi-format export (9:16, 1:1, 16:9)
9. [ ] Mobile optimization
10. [ ] Deploy (Vercel + Railway + MongoDB Atlas + R2)

## Environment Variables

### Backend (.env)
```
ANTHROPIC_API_KEY=sk-ant-oat01-...
VISION_MODEL=claude-sonnet-4-5
TEXT_MODEL=claude-sonnet-4-5
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=videopeen
```

### Frontend (.env.local)
```
GOOGLE_CLIENT_ID=346734901890-b3c...
GOOGLE_CLIENT_SECRET=GOCSPX-...
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=videopeen-nextauth-secret-key-2026
```

## Dev Notes

- Always start MongoDB first: `docker start videopeen-mongo`
- Backend before frontend (port 8000 must be up)
- Close frontend during heavy pipeline runs (OOM risk on 18GB)
- Test videos cleared (31GB freed Feb 22). Need fresh uploads for testing.
- Source videos are in `~/Downloads/Media/Videos/` (Bread Toast 3 MOV + Loaded Fries 5 MOV)
