# Task 006: Transitions (Dissolve/Wipe)

**Priority:** 🟡 HIGH
**Effort:** 3-5 days
**Status:** 🟡 BACKEND COMPLETE (Frontend UI pending)
**Depends on:** Task 002 (Audio) — transitions need audio crossfade too ✅
**Assigned to:** subagent:4fc3fbb2 (backend), awaiting frontend developer

---

## Implementation Status

✅ **Backend Complete** (2026-02-28 14:49 GST)
- xfade filter chain implemented in `video_stitcher.py`
- acrossfade for audio transitions
- Correct offset calculation for chained transitions
- Added `transition_type` and `transition_duration` to project model
- Pipeline integration complete (pipeline.py + render.py)
- See `TASK-006-BACKEND-SUMMARY.md` for full details

⬜ **Frontend Pending**
- Transition type dropdown (None/Fade/Wipe/Slide)
- Transition duration slider (0.3-1.0s)
- UI integration in project settings or editor

---

## Goal

Add smooth transitions between clips instead of hard cuts. Hard cuts feel jarring, especially in cooking content where the mood should flow.

## What To Change

### Backend: `backend/app/services/video_stitcher.py`

Currently clips are concatenated with hard cuts. Add xfade filter between clips.

**ffmpeg xfade filter:**
```bash
# Crossfade between two clips (0.5 sec dissolve)
[v0][v1]xfade=transition=fade:duration=0.5:offset=<clip0_duration-0.5>[vout]
```

**Available transitions (start with these 4):**
- `fade` — Classic dissolve (default)
- `wiperight` — Wipe right
- `slideright` — Slide right
- `smoothleft` — Smooth slide left

**Implementation approach:**
1. After trimming+speeding each clip, apply xfade between consecutive clips instead of simple concat
2. For N clips: need N-1 xfade filters chained
3. Offset calculation: each xfade shortens total by `duration` seconds
4. Audio needs matching `acrossfade` filter

**Filter chain example (3 clips, 0.5s fade):**
```
[v0][v1]xfade=transition=fade:duration=0.5:offset=<dur0-0.5>[xf1];
[xf1][v2]xfade=transition=fade:duration=0.5:offset=<dur0+dur1-1.0>[outv]
```

### Backend: Add transition config to edit plan

- `transition_type`: "none" | "fade" | "wiperight" | "slideright" (default: "fade")
- `transition_duration`: 0.3-1.0 seconds (default: 0.5)
- Store in project document

### Frontend: Transition selector

- Add in project settings or editor page
- Dropdown: None | Fade | Wipe | Slide
- Duration slider: 0.3s - 1.0s

---

## Checklist

- [x] Backend: Implement xfade filter chain in video_stitcher.py
- [x] Backend: Implement acrossfade for audio transitions
- [x] Backend: Add transition_type and transition_duration to project model
- [x] Backend: Calculate correct offsets for chained xfade
- [x] Backend: Pass transition config from pipeline.py and render.py
- [ ] Frontend: Transition type selector
- [ ] Frontend: Transition duration slider
- [ ] Test: 3+ clips with fade transition
- [ ] Test: Transitions with speed ramps
- [ ] Test: No regression on "none" transition (hard cut)

## Technical Notes

- xfade needs ALL inputs to have same pixel format (yuv420p) — already handled
- xfade offset = cumulative duration of previous clips minus transition overlap
- With N clips and duration D: total shortens by (N-1)*D seconds
- acrossfade=d=0.5:c1=tri:c2=tri for audio
- Keep "none" as an option for users who want hard cuts
