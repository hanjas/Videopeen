# Task 019: Prompt Fix — State-Diff + Recipe-Aware Detection

## Context
Read `videopeen/docs/ACTION-DETECTION-FIX.md` for full design context.
Read `backend/app/services/video_analyzer.py` — this is the file you'll modify.

## What to Change

### 1. Update TIMELINE_SYSTEM prompt
Add state-diff instruction to the existing TIMELINE_SYSTEM prompt in `video_analyzer.py`:

Add after the existing CRITICAL RULES section:
```
STATE-DIFF RULE:
- When marking a period as IDLE, compare the scene at the START vs END of the idle period.
- If ANY new ingredient, substance, powder, liquid, or item has appeared that wasn't there before,
  mark it as an ACTION with action_type "inferred_addition" and description
  "[item] appeared — likely added between Xs-Ys" even if you didn't see the hand movement.
- A 40-second "idle" gap in a spice-adding sequence is suspicious — look carefully for changes.
- If the bowl/pot has new content compared to the previous frames, SOMETHING was added.
```

### 2. Update _build_timeline_prompt to include recipe ingredients
The recipe_context dict has `dish_name` and `recipe_steps`. Modify the prompt to emphasize ingredient tracking:

After the RECIPE and STEPS section in the prompt, add:
```
INGREDIENT TRACKING:
The recipe steps above mention specific ingredients. Use them to help identify what you see:
- Match powder colors to expected spices (brown = garam masala/cumin, yellow = turmeric, red/orange = chili, white = salt/sugar/flour)
- If you see fewer ingredient additions than the recipe expects, note which ones were NOT observed
- Add a "missing_ingredients" field to your response listing expected but undetected ingredients
```

### 3. Update the JSON response schema in the prompt
Add to the return JSON schema:
```json
{
  "actions": [...],
  "batch_summary": "...",
  "missing_ingredients": ["list of recipe ingredients not observed in this batch"]
}
```

### 4. Add 1-frame batch overlap
Modify `detect_actions_for_video()` function. Currently batches are non-overlapping:
```python
start_idx = i * batch_size
end_idx = min(start_idx + batch_size, n_frames)
```

Change to include 1 frame overlap:
```python
start_idx = i * batch_size
if i > 0:
    start_idx -= 1  # Include last frame of previous batch
end_idx = min(start_idx + batch_size, n_frames)
```

Also update the prompt text to indicate: "The first frame of this batch overlaps with the last frame of the previous batch for context continuity."

## Files to Modify
- MODIFY: `backend/app/services/video_analyzer.py`

## Testing
- Run existing tests to make sure nothing breaks
- The changes are prompt-only + minor batching logic, so existing behavior should be preserved

## Constraints
- Do NOT change the model being used
- Do NOT change batch_size default
- Do NOT modify any other files
- Keep the existing prompt structure, just ADD to it
- The "missing_ingredients" field should be optional in parsing (don't break if not present)

After implementation, git add, commit with message "feat: state-diff prompt + recipe-aware detection + batch overlap" and push.
