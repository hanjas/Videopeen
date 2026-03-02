# Task 017: Smart Clip Finding — Layer 4 (Full Re-Detection)

## Context
Read `videopeen/docs/SMART-CLIP-FINDING.md` for full design.
Read `backend/app/services/clip_finder.py` for existing Layers 0, 2, 3, 5.
Read `backend/app/services/video_analyzer.py` for the existing action detection pipeline.

## What to Build

### Layer 4: Enhanced Re-Detection
Re-run action detection on relevant video segments with an enhanced prompt that specifically targets the user's search term.

Add to `backend/app/services/clip_finder.py`:

```python
async def full_redetect(
    query: str,
    all_clips: list[dict],
    project_id: str,
) -> list[dict]:
    """Layer 4: Full re-detection with enhanced prompt.
    
    1. Identify source videos from project
    2. Re-run frame extraction + action detection with enhanced prompt
    3. Enhanced prompt includes: "Pay special attention to: {query}"
    4. Diff new detections against existing clips
    5. Return only NEW clips not already in the pool
    """
```

Implementation:
1. Get all source video paths from project upload dir
2. For each video, use the existing frame extraction logic from `video_analyzer.py`
   - But DON'T re-extract all frames if we already have them cached
   - Check `{upload_dir}/{project_id}/frames/` for existing frames
3. Call action detection with modified prompt that emphasizes the search query
4. Compare new detections against existing `all_clips` by time overlap
5. Return clips that are genuinely new (< 50% time overlap with any existing clip)

### Reuse existing pipeline code
Import and reuse from `video_analyzer.py`:
- Frame encoding (`_encode_image`)
- API client creation (`_resolve_api_key`, `_build_async_client`)
- The action detection prompt structure (but modify it)

DO NOT duplicate the full pipeline. Instead, call into the existing functions where possible and only override the detection prompt.

### Enhanced Detection Prompt
```python
ENHANCED_DETECTION_PROMPT = """Analyze these cooking video frames and identify ALL distinct cooking actions.
Pay SPECIAL ATTENTION to any moment involving: {query}

For EACH action, provide:
- action: specific description (be precise about ingredients, spices, tools)
- start_frame: frame number where action begins
- end_frame: frame number where action ends  
- confidence: 0.0-1.0

Be as specific as possible with descriptions. Instead of "stirring pot", say "stirring curry with wooden spoon" or "adding garam masala to pot while stirring".
Label spice/ingredient additions SPECIFICALLY by name when visible.

Return JSON array of actions."""
```

### Update orchestrator
Update `smart_find_clip()`: Layer 0 → Layer 2 → Layer 3 → Layer 4 → Layer 5

## Files to Modify
- MODIFY: `backend/app/services/clip_finder.py`

## Constraints
- Use claude-sonnet-4-5 for re-detection (needs high quality for this)
- Reuse cached frames when available
- Timeout: 120 seconds for the full re-detection
- This is expensive — log cost estimate before running
- If re-detection finds no new clips, move to Layer 5 gracefully
- Mark discovered clips with `"discovered": True, "discovery_layer": 4`
