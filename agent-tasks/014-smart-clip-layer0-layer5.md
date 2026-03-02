# Task 014: Smart Clip Finding — Layer 0 (Regex Search) + Layer 5 (Honest Admission)

## Context
Read `videopeen/docs/SMART-CLIP-FINDING.md` for full design. This task implements the two bookend layers.

## What to Build

### Layer 0: Regex/Fuzzy Search
Add a utility function in a NEW file `backend/app/services/clip_finder.py`:

```python
async def find_clips_by_text(query: str, all_clips: list[dict]) -> list[dict]:
    """Layer 0: Fast regex/fuzzy text search across clip descriptions.
    
    Returns clips sorted by relevance (number of keyword matches).
    Returns empty list if nothing matches.
    """
```

Logic:
1. Split query into keywords (words > 2 chars, lowercased)
2. For each clip, count how many keywords match in the `description` field (case-insensitive)
3. Return clips with score > 0, sorted by score descending
4. Include the match score in a `_search_score` key on each returned clip dict

### Layer 5: Honest Admission Response
Add a function:

```python
def build_not_found_response(query: str) -> dict:
    """Layer 5: Build a helpful 'not found' response with suggestions."""
```

Returns a dict with:
- `type`: "not_found"
- `summary`: A helpful message (see design doc Layer 5 text)
- `suggestions`: List of suggestion strings

### Integration Hook
Add a top-level orchestrator function:

```python
async def smart_find_clip(query: str, all_clips: list[dict], project_id: str = None) -> dict:
    """Main entry point for smart clip finding. Escalates through layers.
    
    Returns:
        {"type": "found", "clips": [...], "layer": 0}
        or
        {"type": "not_found", "summary": "...", "suggestions": [...]}
    """
```

For NOW, this function only does Layer 0 → Layer 5. Later tasks will add Layers 2-4 in between.

## Files to Create/Modify
- CREATE: `backend/app/services/clip_finder.py`
- DO NOT modify `edit_plan.py` yet — integration into refine flow is a separate task

## Testing
Add a simple test: `backend/tests/test_clip_finder.py`
- Test keyword matching with sample clip data
- Test empty results → not_found response
- Test partial keyword matches

## Constraints
- No LLM calls in this task (Layer 0 is pure text matching)
- Keep it simple, clean, well-typed
- Use logging (logger = logging.getLogger(__name__))
