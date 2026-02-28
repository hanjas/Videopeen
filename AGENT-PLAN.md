# Videopeen — Master Build Plan

**Last Updated:** 2026-02-28
**Status:** Phase 1 - Ship-Blocker Fixes

---

## Vision

AI-powered cooking video editor. Upload raw footage → AI edits → social-ready short-form content.
**Target:** Cooking content creators on TikTok/Reels/Shorts.

## Current State (What Works)

- ✅ V6 action-based pipeline (frame extraction → Claude Vision → edit plan → render)
- ✅ Conversational editing ("Remove banana shots" → 16s new preview)
- ✅ Proxy preview system (0.07s instant concat)
- ✅ Undo/redo (timeline snapshots)
- ✅ Google SSO, BYOK API keys, WebSocket progress
- ✅ Dark theme UI (Next.js 14 + Tailwind)

## Actual Benchmarks (Feb 28, 2026)

- 3 videos, 11.9 min footage → **4m 53s** total pipeline
- 356 frames → 103 actions → 18 clips
- Conversational edit → **16s** to new preview
- Proxy concat → **0.07s**

---

## Build Phases

### Phase 1: Ship-Blockers (CURRENT — Week 1-3)

These MUST be done before any user testing. Without these, product is unusable.

| # | Task | Priority | Effort | Status |
|---|------|----------|--------|--------|
| 1 | [Vertical Export (9:16, 1:1)](/agent-tasks/001-vertical-export.md) | 🔴 CRITICAL | 3 days | ⬜ NOT STARTED |
| 2 | [Audio Preservation + Sync](/agent-tasks/002-audio-preservation.md) | 🔴 CRITICAL | 2 weeks | ⬜ NOT STARTED |
| 3 | [Upload Progress Bar](/agent-tasks/004-upload-progress.md) | 🟡 HIGH | 1 day | ⬜ NOT STARTED |

### Phase 2: Competitive Parity (Week 3-6)

What every video editor has. Without these, users leave for CapCut.

| # | Task | Priority | Effort | Status |
|---|------|----------|--------|--------|
| 4 | [Auto-Captions (Whisper)](/agent-tasks/003-auto-captions.md) | 🟡 HIGH | 1 week | ⬜ NOT STARTED |
| 5 | [Text Overlays (ingredients/steps)](/agent-tasks/005-text-overlays.md) | 🟡 HIGH | 1-2 weeks | ⬜ NOT STARTED |
| 6 | [Transitions (dissolve/wipe)](/agent-tasks/006-transitions.md) | 🟡 HIGH | 3-5 days | ⬜ NOT STARTED |
| 7 | [Music Library + Auto-ducking](/agent-tasks/007-music-library.md) | 🟡 HIGH | 1-2 weeks | ⬜ NOT STARTED |
| 8 | [Mobile-Responsive UI](/agent-tasks/008-mobile-responsive.md) | 🟡 HIGH | 2-3 weeks | ⬜ NOT STARTED |
| 9 | [Onboarding / Tutorial](/agent-tasks/009-onboarding.md) | 🟢 MEDIUM | 1 week | ⬜ NOT STARTED |

### Phase 3: Differentiation (Week 8-12)

What makes Videopeen 10x better than generic tools.

| # | Task | Priority | Effort | Status |
|---|------|----------|--------|--------|
| 10 | [Style Presets (Cozy/Fast/Cinematic)](/agent-tasks/010-style-presets.md) | 🟢 MEDIUM | 1-2 weeks | ⬜ NOT STARTED |
| 11 | [Auto-Thumbnail Generation](/agent-tasks/011-auto-thumbnail.md) | 🟢 MEDIUM | 2 days | ⬜ NOT STARTED |
| 12 | [Music Mood Matching (AI picks vibe)](/agent-tasks/012-music-mood.md) | 🟢 MEDIUM | 1 week | ⬜ NOT STARTED |
| 13 | [Batch Project Processing](/agent-tasks/013-batch-processing.md) | 🟢 MEDIUM | 1 week | ⬜ NOT STARTED |
| 14 | [Error Recovery (resume pipeline)](/agent-tasks/014-error-recovery.md) | 🟢 MEDIUM | 1 week | ⬜ NOT STARTED |

### Phase 4: Growth & Distribution (Week 12+)

Social features, posting, analytics.

| # | Task | Priority | Effort | Status |
|---|------|----------|--------|--------|
| 15 | [Direct TikTok/IG Posting](/agent-tasks/015-direct-posting.md) | 🟡 HIGH | 2-3 weeks | ⬜ NOT STARTED |
| 16 | [Multi-Format Export Presets](/agent-tasks/016-multi-format.md) | 🟢 MEDIUM | 1 week | ⬜ NOT STARTED |
| 17 | [Analytics Dashboard](/agent-tasks/017-analytics.md) | 🟢 MEDIUM | 2 weeks | ⬜ NOT STARTED |
| 18 | [Custom Watermark/Logo](/agent-tasks/018-watermark.md) | 🟢 MEDIUM | 3 days | ⬜ NOT STARTED |

### Phase 5: Moonshots (Future)

Revolutionary features that change the game.

| # | Task | Priority | Effort | Status |
|---|------|----------|--------|--------|
| 19 | Live Cooking → Auto-Edit (Real-time pipeline) | 🔵 FUTURE | 2-3 months | ⬜ NOT STARTED |
| 20 | Voice-Driven Editing (Zero UI) | 🔵 FUTURE | 1-2 months | ⬜ NOT STARTED |
| 21 | Reverse Engineer Viral Videos (Style Transfer) | 🔵 FUTURE | 1-2 months | ⬜ NOT STARTED |
| 22 | AI Cooking Coach (Technique Analysis) | 🔵 FUTURE | 2-3 months | ⬜ NOT STARTED |
| 23 | Collaborative Cooking Series (Multi-Creator) | 🔵 FUTURE | 2-3 months | ⬜ NOT STARTED |

---

## Key Architecture Files

| File | Purpose |
|------|---------|
| `backend/app/services/pipeline.py` | Main pipeline orchestrator |
| `backend/app/services/video_analyzer.py` | Claude Vision (action detection + edit plan) |
| `backend/app/services/video_processor.py` | ffmpeg frame extraction |
| `backend/app/services/video_stitcher.py` | ffmpeg clip stitching + speed ramps |
| `backend/app/services/proxy_renderer.py` | 480p proxy pre-render + fast concat |
| `backend/app/services/render.py` | HD render after edit confirmation |
| `backend/app/routers/edit_plan.py` | Edit plan CRUD, refine, undo/redo |
| `backend/app/routers/upload.py` | File upload handling |
| `frontend/app/dashboard/project/[id]/page.tsx` | Main editor page (608 lines) |
| `frontend/lib/api.ts` | API client + WebSocket |

## Key Design Decisions

| Decision | Why |
|----------|-----|
| Claude Vision, not custom ML | Faster to build, cooking domain knowledge built-in |
| Actions as fundamental units | Not scenes/segments — cooking ACTIONS (dice, sear, plate) |
| Proxy pre-render ALL clips | Enables instant re-editing without re-render |
| Conversational editing over timeline UI | Target user is NOT a pro editor |
| ffmpeg for everything | Battle-tested, hardware accel (VideoToolbox), no deps |
| No audio (current) | Scope reduction for MVP — MUST FIX NOW |

## Agent Rules

1. **Read AGENT-STATE.md first** — know where we are
2. **Read your task file** — know exactly what to do
3. **Write code directly** — don't suggest, implement
4. **Update task file checkboxes** — track progress
5. **Update AGENT-STATE.md when done** — next agent knows what happened
6. **Small commits** — one feature = one logical unit
7. **Test with real files** — uploads/ has test videos after pipeline run
8. **Don't break existing features** — conversational editing, proxy system must keep working
