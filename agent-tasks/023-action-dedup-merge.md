# Task 023: Post-Merge Action Deduplication

**Priority:** HIGH
**Scope:** Backend only — `backend/app/services/video_analyzer.py`
**Goal:** Add deduplication logic after merging parallel batch results

---

## Problem

Parallel batches with 1-frame overlap and no `prev_action_hint` cause:
1. Same action detected by adjacent batches (duplicates)
2. One action split into two fragments across batch boundary

## Implementation

Add a `_dedup_actions()` function in `video_analyzer.py` and call it at the end of `detect_actions_for_video()` after merging all batch results.

### Dedup Logic

```python
def _dedup_actions(actions: list[dict], overlap_threshold: float = 0.5) -> list[dict]:
    """Remove duplicate/overlapping actions from merged batch results.
    
    Two actions are considered duplicates if:
    1. They're from the same source video
    2. Their time ranges overlap by >= overlap_threshold (50%)
    3. They have similar descriptions (optional, for safety)
    
    When duplicates found, keep the one with higher visual_quality.
    When fragments found (adjacent, short gap), merge them.
    """
    if not actions:
        return actions
    
    # Sort by start_time
    sorted_actions = sorted(actions, key=lambda a: a.get("start_time", 0))
    
    merged = []
    skip_indices = set()
    
    for i, action_a in enumerate(sorted_actions):
        if i in skip_indices:
            continue
        
        # Check against next few actions for overlap
        for j in range(i + 1, min(i + 5, len(sorted_actions))):
            if j in skip_indices:
                continue
            
            action_b = sorted_actions[j]
            
            # Must be same source video
            if action_a.get("source_video") != action_b.get("source_video"):
                continue
            
            a_start = action_a.get("start_time", 0)
            a_end = action_a.get("end_time", 0)
            b_start = action_b.get("start_time", 0)
            b_end = action_b.get("end_time", 0)
            
            # If b starts after a ends + 2s gap, no overlap possible
            if b_start > a_end + 2.0:
                break
            
            # Calculate overlap
            overlap_start = max(a_start, b_start)
            overlap_end = min(a_end, b_end)
            overlap_duration = max(0, overlap_end - overlap_start)
            
            min_duration = min(a_end - a_start, b_end - b_start)
            if min_duration <= 0:
                continue
            
            overlap_ratio = overlap_duration / min_duration
            
            if overlap_ratio >= overlap_threshold:
                # DUPLICATE: keep higher quality one
                a_quality = action_a.get("visual_quality", 0)
                b_quality = action_b.get("visual_quality", 0)
                
                if b_quality > a_quality:
                    # Replace a with b
                    skip_indices.add(i)
                    break
                else:
                    # Keep a, skip b
                    skip_indices.add(j)
            
            elif overlap_ratio > 0 or (b_start - a_end) < 1.0:
                # FRAGMENT: merge into one action (extend a to cover b)
                action_a["end_time"] = max(a_end, b_end)
                # Keep the better description
                if len(action_b.get("description", "")) > len(action_a.get("description", "")):
                    action_a["description"] = action_b["description"]
                skip_indices.add(j)
        
        if i not in skip_indices:
            merged.append(action_a)
    
    # Re-assign sequential action_ids
    for idx, action in enumerate(merged):
        action["action_id"] = idx
    
    logger.info("Dedup: %d actions → %d actions (%d removed)",
                len(actions), len(merged), len(actions) - len(merged))
    
    return merged
```

### Integration Point

In `detect_actions_for_video()`, after the merge loop that assigns action_ids, add:

```python
# After: logger.info("Detected %d actions in %s", len(all_actions), video_name)
# Add:
all_actions = _dedup_actions(all_actions)
logger.info("After dedup: %d actions in %s", len(all_actions), video_name)
```

## Testing

Verify by checking logs: "Dedup: X actions → Y actions (Z removed)"
If Z > 0, the dedup is working.

## Files Modified
- `backend/app/services/video_analyzer.py`

## DO NOT
- Do not modify pipeline.py
- Do not change batch processing logic
- Do not restart servers
