# Task 024: Switch Phase 1 Action Detection to Haiku

**Priority:** HIGH
**Scope:** Backend only
**Goal:** Use Haiku for Phase 1 (action detection) and keep Sonnet for Phase 2 (edit plan). Also replace keyword reconciliation with a single Haiku LLM call.

---

## Change 1: Use Haiku for Phase 1 Action Detection

**File:** `backend/app/services/video_analyzer.py` → `detect_actions_batch()`

The `detect_actions_batch()` function currently uses `settings.vision_model` (Sonnet) for action detection. Change it to use `settings.fast_vision_model` (Haiku).

Find the `_call_claude_with_retry` call (or `client.messages.create`) inside `detect_actions_batch()` and change the model:

```python
# BEFORE:
model=settings.vision_model,

# AFTER:
model=settings.fast_vision_model,
```

**Important:** Only change Phase 1 (`detect_actions_batch`). Do NOT change Phase 2 (`create_edit_plan`) - that must stay on `settings.text_model` (Sonnet).

---

## Change 2: Replace Keyword Reconciliation with Haiku LLM Call

**File:** `backend/app/services/reconciliation.py`

The current `match_ingredients_to_actions()` function uses pure regex keyword matching against a static list of 80 ingredients. This is brittle - "kashmiri red chili" won't match "chili powder", "tomatoes" won't match "tomato".

Replace the core matching logic with a single Haiku LLM call.

### New Implementation:

Keep the existing function signatures but change the internals of `reconcile_actions_with_recipe()`:

```python
async def reconcile_actions_with_recipe(
    all_actions: list[dict],
    recipe_context: dict,
    frame_results: list[Any],
    video_path_map: dict[str, str],
    api_key: str | None = None,
) -> dict:
    """Compare detected actions against recipe using LLM for smart matching."""
    try:
        logger.info("Starting LLM reconciliation: %d actions, recipe='%s'",
                    len(all_actions), recipe_context.get("dish_name", "Unknown"))
        
        recipe_steps = recipe_context.get("recipe_steps", [])
        if not recipe_steps:
            return {
                "matched_ingredients": [],
                "missing_ingredients": [],
                "suspicious_gaps": [],
                "status": "skipped_no_recipe",
            }
        
        # Still find suspicious gaps (this is pure logic, no LLM needed)
        gaps = find_suspicious_gaps(all_actions, min_gap_seconds=10.0)
        
        # Build action summary for LLM
        action_summaries = []
        for a in all_actions:
            action_summaries.append(
                f"[{a['action_id']}] {a.get('start_time', 0):.1f}-{a.get('end_time', 0):.1f}s: "
                f"{a.get('description', 'unknown')} (type={a.get('action_type', '?')})"
            )
        
        steps_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(recipe_steps))
        actions_text = "\n".join(action_summaries)
        
        prompt = f"""Match detected cooking actions to recipe steps/ingredients.

RECIPE: {recipe_context.get('dish_name', 'Unknown')}
STEPS:
{steps_text}

DETECTED ACTIONS:
{actions_text}

For each ingredient/step in the recipe, find the matching action(s). Consider:
- Synonyms: "tomatoes" = "tomato", "capsicum" = "bell pepper"
- Partial matches: "adding red powder" could be "chili powder" or "paprika"
- Implied ingredients: "making masala paste" implies multiple spices

Return JSON:
{{
  "matched": [
    {{"ingredient": "<name>", "action_id": <int>, "confidence": "high|medium|low"}}
  ],
  "missing": [
    {{"ingredient": "<name>", "suggestion": "<where it might be or why missing>"}}
  ],
  "match_rate": <float 0-100>
}}"""
        
        from app.services.video_analyzer import _build_async_client, _resolve_api_key, _call_claude_with_retry
        from app.config import settings
        
        key = api_key or await _resolve_api_key()
        client = _build_async_client(key)
        
        response = await _call_claude_with_retry(
            client,
            model=settings.fast_vision_model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        
        text = response.content[0].text
        
        # Parse JSON response
        import re
        cleaned = re.sub(r'```(?:json)?\s*', '', text).strip()
        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError:
            # Fallback: try to find JSON object
            start = cleaned.find('{')
            if start != -1:
                depth = 0
                for i in range(start, len(cleaned)):
                    if cleaned[i] == '{': depth += 1
                    elif cleaned[i] == '}':
                        depth -= 1
                        if depth == 0:
                            try:
                                result = json.loads(cleaned[start:i+1])
                            except json.JSONDecodeError:
                                result = None
                            break
                else:
                    result = None
            else:
                result = None
        
        if not result:
            logger.warning("Failed to parse LLM reconciliation response, falling back to keyword matching")
            # Fallback to existing keyword matching
            ingredients = extract_ingredients_from_recipe(recipe_context)
            matched, unmatched = match_ingredients_to_actions(ingredients, all_actions)
            return {
                "matched_ingredients": matched,
                "missing_ingredients": [{"ingredient": u["ingredient"], "suggestion": "No match found"} for u in unmatched],
                "suspicious_gaps": gaps[:10],
                "status": "fallback_keywords",
                "total_ingredients": len(ingredients),
                "match_rate": round(len(matched) / len(ingredients) * 100, 1) if ingredients else 0,
            }
        
        matched = result.get("matched", [])
        missing = result.get("missing", [])
        match_rate = result.get("match_rate", 0)
        
        return {
            "matched_ingredients": matched,
            "missing_ingredients": missing,
            "suspicious_gaps": gaps[:10],
            "status": "completed",
            "total_ingredients": len(matched) + len(missing),
            "match_rate": match_rate,
        }
        
    except Exception as e:
        logger.exception("LLM Reconciliation failed: %s", e)
        # Fallback to keyword matching on any error
        try:
            ingredients = extract_ingredients_from_recipe(recipe_context)
            matched, unmatched = match_ingredients_to_actions(ingredients, all_actions)
            return {
                "matched_ingredients": matched,
                "missing_ingredients": [{"ingredient": u["ingredient"], "suggestion": "No match found"} for u in unmatched],
                "suspicious_gaps": find_suspicious_gaps(all_actions, min_gap_seconds=10.0)[:10],
                "status": "fallback_keywords",
                "total_ingredients": len(ingredients),
                "match_rate": round(len(matched) / len(ingredients) * 100, 1) if ingredients else 0,
            }
        except Exception:
            return {
                "matched_ingredients": [],
                "missing_ingredients": [],
                "suspicious_gaps": [],
                "status": "error",
                "error": str(e),
            }
```

### Important Notes:
- Keep ALL existing functions (`extract_ingredients_from_recipe`, `match_ingredients_to_actions`, `find_suspicious_gaps`, `suggest_missing_ingredient_location`) — they serve as fallback
- Add `import json` at the top if not already there
- Add `api_key: str | None = None` parameter to the function signature
- The LLM call uses `settings.fast_vision_model` (Haiku) — cheap enough for this task

---

## Change 3: Pass api_key to reconciliation

**File:** `backend/app/services/pipeline.py`

In the reconciliation call, pass the already-resolved API key:

Find the call to `reconcile_actions_with_recipe` and add `api_key=pipeline_api_key`:

```python
reconciliation = await reconcile_actions_with_recipe(
    all_actions, recipe_context, all_frame_results, video_path_map,
    api_key=pipeline_api_key,
)
```

(The `pipeline_api_key` variable should already exist from Task 022's Bug 5 fix.)

---

## Testing

After implementation:
1. Check logs for Phase 1 — should show Haiku model being used
2. Check logs for reconciliation — should show LLM call instead of keyword matching
3. Compare output quality with a test video
4. Check API costs — should be significantly lower

## Files Modified
- `backend/app/services/video_analyzer.py` (Change 1)
- `backend/app/services/reconciliation.py` (Change 2)
- `backend/app/services/pipeline.py` (Change 3)

## DO NOT
- Do not change Phase 2 (edit plan) model — keep it on Sonnet
- Do not remove existing keyword matching functions (they're the fallback)
- Do not modify frontend code
- Do not restart servers
