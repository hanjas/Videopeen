# Proxy Clip System (LEGO Blocks) - Test Plan

## Overview
The Proxy Clip System pre-renders each clip as a 480p "LEGO block" and uses fast concatenation (2-3 sec) instead of full re-renders (2-3 min) on every edit.

## Files Modified

### Backend
1. **NEW**: `backend/app/services/proxy_renderer.py`
   - `pre_render_proxy_clips()` - Pre-render clips in parallel (max 3 concurrent)
   - `fast_concat_proxies()` - Concat using ffmpeg demuxer (no re-encoding)
   - `get_existing_proxies()` - Check which clips already have proxies
   - `identify_new_clips()` - Find clips that need new proxies

2. **MODIFIED**: `backend/app/services/pipeline.py`
   - Added proxy pre-rendering step after edit plan creation
   - Creates proxy preview alongside HD render
   - Saves proxy paths in edit_plan document

3. **MODIFIED**: `backend/app/routers/edit_plan.py`
   - Refine endpoint now uses proxies for instant preview
   - Only renders NEW clips (reuses existing proxies)
   - Added undo/redo endpoints with timeline snapshots
   - Added proxy preview endpoint: `GET /api/projects/{id}/edit-plan/preview`
   - Saves timeline snapshots before each refine for undo/redo

### Frontend
4. **MODIFIED**: `frontend/lib/api.ts`
   - Added `getProxyPreview()` method
   - Added `undoEdit()` method
   - Added `redoEdit()` method

5. **MODIFIED**: `frontend/app/dashboard/project/[id]/page.tsx`
   - Shows proxy video immediately after refine
   - Displays "HD rendering..." badge while HD processes
   - Swaps to HD seamlessly when ready via WebSocket
   - Added Undo/Redo buttons
   - Shows change summary toast

## Test Plan

### Test 1: Initial Pipeline with Proxies
**Goal**: Verify proxies are created during initial pipeline run

1. Upload a new video to a project
2. Start processing
3. Check logs for proxy rendering step (should see "Pre-rendering X proxy clips")
4. Verify proxy files exist in `uploads/{project_id}/proxies/`
5. Verify `proxy_preview_path` is saved in edit_plan document
6. Check that both proxy preview and HD final video are created

**Expected**:
- All clips (timeline + pool) have proxies rendered
- Proxy files are 480p, ~28 CRF, fast preset
- Proxy preview concat happens in 2-3 seconds
- HD render still completes as before

### Test 2: Fast Edit with Proxy Reuse
**Goal**: Verify existing proxies are reused, only new clips are rendered

1. Complete Test 1 (have a project with proxies)
2. Send refine instruction: "Remove the first clip"
3. Check logs - should NOT re-render proxies for existing clips
4. Proxy preview should update in 2-3 seconds
5. HD render happens in background

**Expected**:
- No proxy re-rendering (or minimal if new clips added)
- Proxy preview URL returned immediately
- Frontend shows proxy video instantly
- "HD rendering..." badge appears
- When HD ready, video swaps seamlessly

### Test 3: Undo/Redo
**Goal**: Verify undo/redo works with instant proxy loading

1. Complete Test 2 (have edited timeline)
2. Click "Undo" button
3. Should see previous proxy video load instantly (2-3 sec)
4. Click "Redo" button
5. Should return to edited version instantly

**Expected**:
- Undo loads previous timeline snapshot
- Proxy concat happens fast (no re-rendering)
- Redo works to go forward
- At version 1, undo should error gracefully
- At latest version, redo should error gracefully

### Test 4: Multiple Rapid Edits
**Goal**: Stress test the system with many quick edits

1. Complete Test 1
2. Send 5 refine instructions rapidly:
   - "Make it 30 seconds"
   - "Remove boring parts"
   - "Add more close-ups"
   - "Speed up the middle section"
   - "Remove the ending"

**Expected**:
- Each edit returns proxy preview immediately
- Timeline snapshots saved for each version
- Can undo/redo through all versions
- HD renders queue in background (may lag behind proxies)
- No crashes or memory issues (18GB RAM, max 3 concurrent renders)

### Test 5: Clip Pool Integration
**Goal**: Verify clips from pool get proxies when added to timeline

1. Complete Test 1
2. Send instruction: "Add the unused close-up shot"
3. Check if clip from pool is used
4. Verify proxy already exists (from initial pipeline) OR is rendered quickly

**Expected**:
- If clip was in pool, proxy already exists → instant concat
- If new custom trim, proxy renders quickly
- No duplicate proxy rendering

### Test 6: Proxy Format Compatibility
**Goal**: Ensure all proxies have same format for concat demuxer

1. Complete Test 1
2. Check all proxy files in `uploads/{project_id}/proxies/`
3. Run: `ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height,pix_fmt {proxy_file}`

**Expected** (for all proxies):
- Codec: h264
- Height: 480
- Width: proportional (scale=-2:480)
- Pixel format: yuv420p

### Test 7: Speed Factor Handling
**Goal**: Verify speed factors are baked into proxy clips

1. Complete Test 1
2. Send instruction: "Speed up the chopping part to 2x"
3. Verify proxy is re-rendered with speed applied
4. Check concat works with mixed speed proxies

**Expected**:
- Proxy with speed factor is re-rendered
- Speed is baked into proxy via setpts filter
- Fast concat still works (all proxies same format)

### Test 8: Error Handling
**Goal**: Verify graceful degradation on proxy failures

1. Delete a proxy file manually
2. Try to refine edit plan
3. Check logs for warnings
4. Verify system falls back gracefully (or re-renders missing proxy)

**Expected**:
- Warning logged for missing proxy
- System either re-renders missing proxy or skips it
- Frontend shows error toast if concat fails
- HD render still works as fallback

## Performance Benchmarks

### Before Proxy System:
- Full re-render on edit: **2-3 minutes**
- User waits entire time for preview

### After Proxy System:
- Initial pipeline: +10-20 seconds (proxy pre-rendering)
- Edit with proxy reuse: **2-3 seconds** (99% faster!)
- Edit with new clips: ~10-15 seconds (render new + concat)

### Memory Usage:
- Max 3 concurrent ffmpeg processes
- Each proxy render: ~500MB-1GB RAM
- Total: ~2-3GB max concurrent (safe on 18GB)

## Known Limitations

1. **First-time pipeline is slightly slower** (pre-rendering all proxies)
2. **Proxy quality is lower (480p)** - but HD version follows
3. **Concat demuxer requires same format** - ensured by pre-render step
4. **Timeline snapshots grow over time** - may need cleanup later

## Success Criteria

✅ Initial pipeline creates proxies for all clips  
✅ Refine returns proxy preview in <5 seconds  
✅ HD render happens in background without blocking  
✅ Undo/redo work instantly with proxies  
✅ No memory issues with 18GB RAM  
✅ Existing full-render pipeline still works  

## Next Steps (Future Enhancements)

- [ ] Add proxy quality setting (360p/480p/720p)
- [ ] Cleanup old timeline snapshots (keep last 10?)
- [ ] Add "Export Proxy" option for faster social media exports
- [ ] Implement smart proxy caching (persist across restarts)
- [ ] Add visual indicator showing proxy vs HD quality
