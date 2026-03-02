# Task 021: Reconciliation Phase — Recipe vs Detected Actions

## Context
Read `videopeen/docs/ACTION-DETECTION-FIX.md` for full design context.
Read `backend/app/services/pipeline.py` — understand where actions are detected and the edit plan is created.
Read `backend/app/services/video_analyzer.py` — understand the action detection output format.

## What to Build

### New service: `backend/app/services/reconciliation.py`

After action detection (Phase 1) and before edit planning (Phase 2), add a reconciliation step that compares detected actions against recipe ingredients.

```python
async def reconcile_actions_with_recipe(
    all_actions: list[dict],
    recipe_context: dict,
    frame_results: list,  # DenseFrameResult list for re-scanning gaps
    video_path_map: dict[str, str],
) -> dict:
    """Compare detected actions against recipe to find missing ingredients.
    
    Returns:
        {
            "matched_ingredients": [{"ingredient": "turmeric", "action_id": 5, "confidence": "high"}],
            "missing_ingredients": [{"ingredient": "garam masala", "nearest_candidate": {...}, "suggestion": "..."}],
            "suspicious_gaps": [{"start": 129.0, "end": 169.0, "duration": 40.0, "context": "between salt and flour additions"}],
        }
    """
```

### Implementation

#### Step 1: Extract ingredients from recipe steps
```python
def extract_ingredients_from_recipe(recipe_context: dict) -> list[str]:
    """Parse recipe steps to extract ingredient names."""
    # Use simple keyword extraction from recipe_steps
    # Common cooking ingredients, spices, etc.
    # Return list of ingredient names
```

#### Step 2: Match ingredients to detected actions
```python
def match_ingredients_to_actions(
    ingredients: list[str],
    actions: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Match recipe ingredients to detected actions.
    Returns (matched, unmatched) ingredient lists.
    """
    # For each ingredient, search action descriptions for mentions
    # Use fuzzy matching (ingredient keywords in description)
    # Return matched with action_id, and unmatched
```

#### Step 3: Find suspicious gaps
```python
def find_suspicious_gaps(
    actions: list[dict],
    min_gap_seconds: float = 10.0,
) -> list[dict]:
    """Find suspiciously long idle gaps between actions.
    
    A 40-second gap in a spice-adding sequence is suspicious.
    """
    # Sort actions by video and start_time
    # Find gaps > min_gap_seconds
    # Flag gaps where adjacent actions are brief (ingredient additions)
```

#### Step 4: Generate suggestions for missing ingredients
For each missing ingredient, find the nearest candidate:
- Check if any "idle" action descriptions mention the ingredient's expected appearance
- Check suspicious gaps that might contain the missing addition
- Generate user-facing suggestion text

### Integration into pipeline.py

After the action detection loop (after "Total actions detected" log), add:

```python
# Reconciliation: compare detected actions against recipe
from app.services.reconciliation import reconcile_actions_with_recipe

reconciliation = await reconcile_actions_with_recipe(
    all_actions, recipe_context, all_frame_results, video_path_map
)

# Log findings
if reconciliation["missing_ingredients"]:
    logger.warning("Reconciliation: %d recipe ingredients not detected: %s",
                   len(reconciliation["missing_ingredients"]),
                   [m["ingredient"] for m in reconciliation["missing_ingredients"]])

if reconciliation["suspicious_gaps"]:
    logger.info("Reconciliation: %d suspicious gaps found",
                len(reconciliation["suspicious_gaps"]))

# Save reconciliation to DB alongside the edit plan
```

Also save reconciliation results in the edit_plan document so the frontend can show warnings like "Garam masala expected but not detected."

### What to store in DB
Add to the edit_plan_doc in pipeline.py:
```python
"reconciliation": {
    "matched_ingredients": [...],
    "missing_ingredients": [...],
    "suspicious_gaps": [...],
}
```

## Files to Create/Modify
- CREATE: `backend/app/services/reconciliation.py`
- MODIFY: `backend/app/services/pipeline.py` (add reconciliation step after action detection)

## Constraints
- NO LLM calls — this is pure text matching and gap analysis
- Keep it simple: keyword matching for ingredient identification
- Don't block the pipeline if reconciliation fails (try/except)
- Log clearly but don't slow down the pipeline

After implementation, git add, commit with message "feat: reconciliation phase - recipe vs detected actions" and push.
