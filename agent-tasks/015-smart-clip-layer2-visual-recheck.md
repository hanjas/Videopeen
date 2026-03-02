# Task 015: Smart Clip Finding — Layer 2 (Visual Re-Check)

## Context
Read `videopeen/docs/SMART-CLIP-FINDING.md` for full design.
Read `backend/app/services/clip_finder.py` (created in Task 014) for the existing framework.

## What to Build

### Layer 2: Visual Re-Check of Candidate Clips
When Layer 1 (semantic match via Claude in refine) returns low-confidence or no results, we take the top candidates and visually verify them by extracting frames and asking a vision model.

Add to `backend/app/services/clip_finder.py`:

```python
async def visual_recheck_clips(
    query: str,
    candidate_clips: list[dict],
    project_id: str,
    max_candidates: int = 8,
) -> list[dict]:
    """Layer 2: Extract frames from candidate clips and verify visually.
    
    For each candidate:
    1. Extract 3 frames (start, middle, end) from the clip's time range
    2. Send to Claude vision with a focused prompt
    3. Return clips where vision confirms the match
    """
```

Implementation:
1. For each candidate clip (up to max_candidates):
   - Determine source video path from `project_id` and clip's `source_video`
   - Use ffmpeg to extract 3 frames at start, midpoint, and end of clip's time range
   - Encode frames as base64
2. Send ALL frames in a single Claude API call with prompt:
   ```
   I'm searching for: "{query}" in a cooking video.
   Below are frames from {n} candidate clips. For each clip, tell me if it matches.
   Respond as JSON: [{"clip_index": 0, "matches": true/false, "confidence": 0.0-1.0, "reason": "..."}]
   ```
3. Parse response, return clips where matches=true and confidence > 0.6
4. Add `_visual_score` to returned clips

### Update the orchestrator
Update `smart_find_clip()` to include Layer 2 between Layer 0 and Layer 5:
- Layer 0 → if not found → Layer 2 (pass all_clips as candidates, sorted by keyword partial match) → Layer 5

### Dependencies
- `backend/app/services/video_analyzer.py` — reuse `_resolve_api_key`, `_build_async_client`, `_encode_image`
- `backend/app/config.py` — for `settings.upload_dir`
- ffmpeg must be available on PATH

### Frame Extraction Helper
Add a helper in `clip_finder.py`:

```python
async def _extract_clip_frames(
    video_path: str, start_time: float, end_time: float, num_frames: int = 3
) -> list[str]:
    """Extract frames from a clip's time range, return list of temp file paths."""
```

Use ffmpeg subprocess (asyncio.create_subprocess_exec). Output to temp dir. Clean up after use.

## Files to Modify
- MODIFY: `backend/app/services/clip_finder.py`

## Constraints
- Use claude-haiku-3-5 for vision (cheaper, fast enough for verification)
- Single API call for all candidates (batch frames together)
- Clean up temp frame files after use
- Timeout: 30 seconds for the vision call
- If API call fails, log warning and return empty (don't crash the search)
