# Task 018: Smart Clip Finding — Integration into Refine Flow

## Context
Read `videopeen/docs/SMART-CLIP-FINDING.md` for full design.
Read `backend/app/services/clip_finder.py` for all layers (Tasks 014-017).
Read `backend/app/routers/edit_plan.py` — the `refine_edit_plan` function (line ~760).

## What to Build

### Integration into the refine endpoint
Modify `refine_edit_plan()` in `edit_plan.py` to use smart clip finding when Claude's refine response indicates it couldn't find a clip.

#### Detection of "not found" scenario
After Claude returns its tool response, check if:
1. Mode is "propose" AND candidates list is empty or all candidates have low relevance
2. Mode is "apply" but the summary mentions "couldn't find" / "no matching clip" / "not in the pool"
3. Mode is "propose" and summary contains uncertainty language about clip matching

#### Smart search trigger
When a not-found scenario is detected:

```python
from app.services.clip_finder import smart_find_clip

# If Claude couldn't find the clip, try smart search
if should_trigger_smart_search(result):
    all_clips = timeline_clips + clip_pool
    search_result = await smart_find_clip(
        query=body.instruction,
        all_clips=all_clips,
        project_id=project_id,
    )
    
    if search_result["type"] == "found":
        # Re-run Claude's refine with the found clips injected into context
        # Add found clips to the pool text with a note
        extra_pool = format_found_clips(search_result["clips"])
        # Rebuild prompt with extra pool and re-call Claude
        ...
    elif search_result["type"] == "not_found":
        # Return Layer 5 honest admission to frontend
        ...
```

#### Smart search can also be triggered proactively
Before calling Claude, run Layer 0 (regex) on the user's instruction. If it finds strong matches, boost those clips to the top of the pool text sent to Claude. This is free and improves Claude's ability to find the right clip.

```python
# Pre-search boost (Layer 0 only, before Claude call)
from app.services.clip_finder import find_clips_by_text

pre_matches = await find_clips_by_text(body.instruction, clip_pool)
if pre_matches:
    # Move matched clips to top of pool, add "[LIKELY MATCH]" prefix
    ...
```

### New endpoint for manual smart search
Add a new endpoint for when the user explicitly asks to search:

```python
@router.post("/smart-search")
async def smart_search_clip(project_id: str, body: SmartSearchRequest, request: Request):
    """Explicitly trigger smart clip finding."""
```

This allows the frontend to add a "Search harder" button in the future.

### Frontend changes: NOT in this task
Frontend integration is separate. This task only handles the backend wiring.

### WebSocket progress updates
For Layer 3+ (which takes >5 seconds), send progress updates via WebSocket:

```python
await ws_manager.broadcast(project_id, {
    "type": "smart_search_progress",
    "layer": 3,
    "message": "Scanning video gaps for your clip..."
})
```

## Files to Modify
- MODIFY: `backend/app/routers/edit_plan.py`
- Add SmartSearchRequest model to the file

## Constraints
- Layer 0 pre-boost runs on EVERY refine call (it's free)
- Full smart search only triggers when Claude fails to find a clip
- Don't block the refine response waiting for Layer 3+ — return intermediate result and continue searching in background if needed
- Log all smart search triggers with timing
- Add new clips found by smart search to the project's clip_pool in DB
