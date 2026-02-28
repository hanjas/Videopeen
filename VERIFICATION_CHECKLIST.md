# Videopeen V2 Redesign - Verification Checklist

## Pre-Launch Testing

### 1. Backend Pipeline Auto-Render
- [ ] Start backend: `cd backend && uvicorn app.main:app --reload`
- [ ] Upload a cooking video via frontend
- [ ] Verify status flow in DB:
  - `PROCESSING` → `ANALYZING` → `SELECTING` → `STITCHING` → `COMPLETED`
  - **Should NOT show `REVIEW` status**
- [ ] Check MongoDB `edit_plans` collection has saved edit plan
- [ ] Check output video exists at `output_path`
- [ ] Verify WebSocket updates show correct progress

### 2. Conversational Edit Endpoint
- [ ] Test endpoint directly with curl:
```bash
curl -X POST http://localhost:8000/api/projects/{PROJECT_ID}/edit-plan/refine \
  -H "Content-Type: application/json" \
  -H "x-user-email: test@example.com" \
  -d '{"instruction": "Remove the first clip"}'
```
- [ ] Verify response contains:
  - `success: true`
  - `version` incremented
  - `clips_count`
  - `total_duration`
- [ ] Check DB:
  - Edit plan version bumped
  - History array has new entry with instruction
  - Timeline clips updated
- [ ] Verify re-render triggered (check logs for "Render started")
- [ ] Test various instructions:
  - "Make it 30 seconds"
  - "Remove idle moments"
  - "Add the close-up shot"
  - "Reorder: start with plating"

### 3. Frontend Conversational UI
- [ ] Start frontend: `cd frontend && npm run dev`
- [ ] Navigate to completed project page
- [ ] Verify layout:
  - Video auto-plays at top
  - "Export Video" button prominent
  - Conversational edit section below
  - "Advanced Edit" link at bottom
- [ ] Test conversational editing:
  - Type instruction in input
  - Click "Send"
  - Verify chat bubble appears (user message)
  - Verify loading state shows ("Re-editing...")
  - Wait for WebSocket update
  - Verify system response appears
  - Verify video player updates with new output
- [ ] Test multiple refinements in sequence
- [ ] Verify conversation history persists during session

### 4. Integration Testing
- [ ] Complete flow: Upload → Wait → Video plays → Refine → Export
- [ ] Test with different video lengths (30s, 60s, 120s)
- [ ] Test with multiple uploaded videos (multi-angle)
- [ ] Verify old review page still accessible via "Advanced Edit"
- [ ] Test backward compat: Old projects should still work

### 5. Error Handling
- [ ] Test with invalid instruction (nonsensical)
- [ ] Test with empty instruction
- [ ] Test with API key missing
- [ ] Test when Claude returns invalid JSON
- [ ] Verify error messages show in UI
- [ ] Verify system doesn't crash on edge cases

### 6. Performance
- [ ] Measure pipeline time (should be unchanged)
- [ ] Measure refine latency:
  - Claude API call: ~2-5s
  - Re-render: ~10-30s
  - Total: ~15-35s
- [ ] Check token usage in logs (should be ~1500-2500 tokens/refine)
- [ ] Verify no memory leaks (check with multiple refinements)

### 7. Database State
- [ ] Verify edit_plans collection structure:
  - `timeline.clips` array
  - `clip_pool` array
  - `video_path_map` object
  - `history` array
  - `version` number
  - `status`: "draft" | "confirmed" | "completed"
- [ ] Verify edit_decisions updated for backward compat
- [ ] Check indexes for performance

### 8. API Key Resolution
- [ ] Test with user's saved API key in DB
- [ ] Test with ANTHROPIC_API_KEY env var
- [ ] Test with OAuth token (sk-ant-oat*)
- [ ] Verify headers sent correctly:
  - `anthropic-beta: claude-code-20250219,oauth-2025-04-20`
  - `user-agent: claude-cli/1.0.0 (external, cli)`
  - `x-app: cli`

---

## Quick Smoke Test

**Fastest way to verify everything works:**

1. Start backend: `cd backend && uvicorn app.main:app --reload`
2. Start frontend: `cd frontend && npm run dev`
3. Upload a test cooking video
4. Wait for auto-render (~2-5 min)
5. See video auto-play
6. Type: "Make it 30 seconds"
7. Wait for re-render (~30s)
8. Verify new video is shorter
9. Click "Export Video"

**Expected result:** ✅ All steps work without errors

---

## Rollback Plan

If critical issues found:

1. **Revert pipeline auto-render:**
   - In `pipeline.py`, replace auto-stitch logic with old REVIEW stop
   - Restore old flow: `SELECTING → REVIEW → (wait for confirm) → STITCHING`

2. **Disable refine endpoint:**
   - Comment out `@router.post("/refine")` endpoint
   - Frontend will show error on Send, but won't crash

3. **Revert frontend:**
   - Restore old project page from git
   - Or comment out conversational edit section

**Git tags for rollback:**
- Tag current state as `v2-redesign-deployed`
- Previous stable: `v1-review-flow`

---

## Known Issues / Limitations

1. **Clip metadata matching:**
   - Matching clips by source_video + timing (±0.5s tolerance)
   - New custom trims generate new clip_id (no thumbnail)
   - **Impact:** Low. Most edits reuse existing clips.

2. **Claude instruction understanding:**
   - Vague instructions may not work: "Make it better"
   - Specific instructions work best: "Remove clip 3"
   - **Mitigation:** Show examples in placeholder text

3. **Duration precision:**
   - Claude sometimes overshoots target duration
   - Safeguard trims if total > target + 5s
   - **Mitigation:** User can refine again: "Make it shorter"

4. **No undo:**
   - Each refine creates new version (tracked in history)
   - No UI for reverting to previous version
   - **Future:** Add version picker in Advanced Edit

---

## Success Criteria

- ✅ Pipeline completes without REVIEW stop
- ✅ Video auto-plays after completion
- ✅ Conversational edit accepts instruction
- ✅ Re-render completes successfully
- ✅ Export button downloads video
- ✅ No breaking changes to existing features
- ✅ Performance within acceptable range (<10% regression)

---

## Deployment Notes

### Environment Variables Required
```bash
ANTHROPIC_API_KEY=sk-ant-...  # Or user's saved key in DB
MONGODB_URI=mongodb://...
TEXT_MODEL=claude-sonnet-4-5  # Used for refine endpoint
VISION_MODEL=claude-sonnet-4-5  # Used for action detection
```

### Database Migrations
None required. Schema is backward compatible.

### Monitoring
- Watch Claude API usage (new refine calls)
- Monitor re-render job queue (background tasks)
- Track refine latency (should be <30s)
- Check error rates on /refine endpoint

---

**Ready for QA:** ✅  
**Deployment approval:** Pending testing
