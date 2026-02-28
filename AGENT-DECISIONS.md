# Videopeen — Decision Log

Decisions made and WHY. New agents: read this to understand our thinking.

---

## Architecture Decisions

### 2026-02-22: Action-Based Pipeline (V6)
**Decision:** Treat cooking as sequence of ACTIONS, not scenes/segments.
**Why:** PySceneDetect useless for single-take cooking (no hard cuts). Actions (chop, sear, plate) are the natural unit for cooking content.
**Alternative rejected:** Scene detection, per-frame analysis (too slow, too dumb).

### 2026-02-22: Claude Vision for Everything
**Decision:** Use Claude Sonnet 4.5 for both vision analysis AND edit decisions.
**Why:** Single model understands cooking domain. No training data needed. Faster iteration.
**Alternative rejected:** Custom ML models (too expensive to train, no cooking dataset).

### 2026-02-22: Proxy Pre-render ALL Clips
**Decision:** Pre-render every detected action at 480p, not just selected clips.
**Why:** Enables instant re-editing. User says "add plating shots" → clips already rendered, just concat.
**Trade-off:** More disk space + initial render time, but editing is 0.07s instead of minutes.

### 2026-02-22: Conversational Editing over Timeline
**Decision:** Natural language as primary edit interface.
**Why:** Target user is NOT a pro editor. "Remove boring parts" > timeline scrubbing.
**Escape hatch:** Advanced edit page still exists for power users (review/page.tsx).

### 2026-02-28: No File Cleanup (For Now)
**Decision:** Keep all frames, proxies, original videos on disk permanently.
**Why:** Frames used for thumbnails, proxies for undo/redo editing, originals for re-render. Cleanup would break editing flow.
**Future:** Add "archive project" status that cleans proxies/frames but keeps originals.

---

## Feature Decisions

### 2026-02-28: Vertical Export Before Audio
**Decision:** Build 9:16 export first, then audio.
**Why:** Vertical export is 3 days, audio is 2 weeks. Quick win proves progress. Also: silent vertical video > landscape video with sound (for TikTok, auto-play is muted anyway).

### 2026-02-28: No File Size Limit on Upload
**Decision:** Skip upload size limit for now.
**Why:** We're pre-launch, only internal testing. Add limit before public beta.

### 2026-02-28: Agent Coordination via Files
**Decision:** Use markdown files (AGENT-STATE.md, task files) for multi-agent coordination.
**Why:** Files persist across sessions. Agents wake up, read state, continue. No external DB needed.
**Key principle:** Agent brain = files. Session dies, files survive.

---

## Pricing Decisions (Planned)

### 2026-02-28: 4-Tier Model
**Decision:** Free (BYOK) → Creator ($15) → Pro ($40) → Enterprise ($200+)
**Why:** Agent review suggested $25 too high for hobbyists, too low for pros. Tiered model captures all segments.
**Revisit after:** Beta user feedback on willingness to pay.
