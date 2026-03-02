# Task 014: Propose Mode for Conversational Editing

## Goal
Add a "propose" mode to the refine chat so Claude discusses ambiguous edits with the user before applying, while still editing immediately for clear instructions.

## Current System
- File: `backend/app/routers/edit_plan.py`
- `/refine` endpoint takes user instruction, sends to Claude with `apply_edit` tool
- Claude always returns a new timeline immediately (no discussion)
- System prompt at line 33: `REFINE_SYSTEM_PROMPT`
- Tool schema at line 65: `REFINE_TOOL`
- Clip pool limited to 20 clips (line ~720)
- Conversation history limited to 6 messages / 3 turns (line ~726)

## Implementation Plan

### Step 1: Update Tool Schema (REFINE_TOOL)

Replace the current `REFINE_TOOL` with:

```python
REFINE_TOOL = {
    "name": "apply_edit",
    "description": "Apply video edit changes or propose candidates for user confirmation",
    "input_schema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["apply", "propose"],
                "description": "apply = execute edit immediately. propose = show candidates and ask user to confirm before editing."
            },
            "summary": {
                "type": "string",
                "description": "For apply: 1-3 sentence cooking-aware summary of changes. For propose: explain what you found and what you need the user to decide."
            },
            "clips": {
                "type": "array",
                "description": "Required for 'apply' mode. The full new timeline.",
                "items": {
                    "type": "object",
                    "properties": {
                        "clip_ref": {
                            "type": "string",
                            "description": "Reference like T0, T1 (timeline) or P0, P1 (pool)"
                        },
                        "start_time": {"type": "number"},
                        "end_time": {"type": "number"},
                        "speed_factor": {
                            "type": "number",
                            "enum": [0.5, 0.75, 1.0, 1.5, 2.0, 4.0]
                        },
                        "description": {"type": "string"},
                        "source_hint": {
                            "type": "string",
                            "description": "First 8 chars of source video filename"
                        }
                    },
                    "required": ["clip_ref", "start_time", "end_time", "speed_factor", "description"]
                }
            },
            "candidates": {
                "type": "array",
                "description": "For 'propose' mode: clips the user should choose between. Include clip_ref so frontend can show thumbnails.",
                "items": {
                    "type": "object",
                    "properties": {
                        "clip_ref": {
                            "type": "string",
                            "description": "Reference like P0, P5, T3 etc."
                        },
                        "description": {
                            "type": "string",
                            "description": "What this clip shows"
                        },
                        "reason": {
                            "type": "string", 
                            "description": "Why this could match what the user asked for"
                        }
                    },
                    "required": ["clip_ref", "description", "reason"]
                }
            },
            "proposed_action": {
                "type": "string",
                "description": "For 'propose' mode: describe what you plan to do once user confirms (e.g., 'Place selected clip before T3 (flour adding)')"
            },
            "warnings": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional warnings about issues or impossible requests"
            }
        },
        "required": ["mode", "summary"]
    }
}
```

### Step 2: Update System Prompt

Add this section to REFINE_SYSTEM_PROMPT (after the existing EDITING RULES section):

```
RESPONSE STRATEGY:
You have two modes: "apply" (execute edit) and "propose" (discuss first).

Use "apply" when:
- The instruction maps to exactly one clear action
- References are unambiguous (e.g., "last clip", "the plating shot", a specific T/P ref)
- The instruction is structural ("make it shorter", "speed up chopping parts", "swap T2 and T5")
- Only one clip in the pool clearly matches the user's description
- User is confirming a previous proposal ("yes use P5", "the first one", "haa")

Use "propose" when:
- A description matches multiple clips with similar relevance ("the salt scene" could be P0 or P1)
- No clip clearly matches the user's description
- The instruction would restructure >50% of the timeline
- The instruction conflicts with cooking video rules and you need to explain the tradeoff

When proposing:
- Include candidate clip_refs so the frontend can show thumbnails
- Explain WHY each candidate might match
- Describe your proposed_action (what you'll do once they confirm)
- Keep it concise - 2-3 candidates max

IMPORTANT: Bias toward action. When in doubt between a confident apply and a proposal, apply.
Users prefer fixing a wrong edit (undo takes 1 click) over answering questions.
Only propose when you genuinely cannot determine user intent.

After a user confirms a proposal, apply immediately - don't re-ask.
If user says "undo", "nevermind", "cancel" - revert to previous timeline version.
```

### Step 3: Update `/refine` Handler

In the `refine_edit_plan` function, after getting Claude's response, branch on mode:

```python
result = tool_block.input
mode = result.get("mode", "apply")

if mode == "propose":
    # Don't render anything - just return the proposal
    candidates = result.get("candidates", [])
    
    # Enrich candidates with thumbnail info
    enriched_candidates = []
    for cand in candidates:
        clip_ref = cand.get("clip_ref", "")
        source_clip = resolve_single_clip_ref(clip_ref, included_clips, clip_pool)
        if source_clip:
            cand["start_time"] = source_clip.get("start_time", 0)
            cand["end_time"] = source_clip.get("end_time", 0)
            cand["visual_quality"] = source_clip.get("visual_quality", 5)
            cand["source_video"] = source_clip.get("source_video", "")
            # Thumbnail ID for frontend to load
            cand["action_id"] = source_clip.get("action_id", "")
        enriched_candidates.append(cand)
    
    # Save conversation (user message + AI proposal)
    # ... (same conversation saving logic as current)
    
    return {
        "type": "proposal",
        "summary": result.get("summary", ""),
        "candidates": enriched_candidates,
        "proposed_action": result.get("proposed_action", ""),
        "warnings": result.get("warnings", []),
    }

elif mode == "apply":
    # Current flow - resolve clips, render proxy, return edit
    # ... (existing code stays the same)
```

**Important:** The proposal response should NOT trigger proxy re-rendering. It's just a chat message.

### Step 4: Increase Clip Pool to 50

Change line ~720 (where pool_text is built):
```python
# Was: clip_pool[:20]
# Now: clip_pool[:50]
pool_text = "\n".join([
    f"[P{i}] {c.get('start_time', 0):.1f}-{c.get('end_time', 0):.1f}s | "
    f"q:{c.get('visual_quality', 0)}/10 | "
    f"src:{c.get('source_video', '?')[:8]} | "
    f"{c.get('description', 'Action')}"
    for i, c in enumerate(clip_pool[:50])
])
```

### Step 5: Keyword Boost for Clip Pool

Before building pool_text, sort clip_pool to boost keyword matches:

```python
# Extract keywords from user instruction
instruction_lower = body.instruction.lower()
keywords = [w for w in instruction_lower.split() if len(w) > 2]

# Score each pool clip by keyword relevance
def keyword_score(clip):
    desc = clip.get("description", "").lower()
    return sum(1 for k in keywords if k in desc)

# Sort: keyword matches first, then by visual_quality
clip_pool_sorted = sorted(
    clip_pool,
    key=lambda c: (-keyword_score(c), -c.get("visual_quality", 0))
)
```

### Step 6: Increase Conversation History to 10 messages (5 turns)

Change:
```python
# Was: recent_msgs = active_convo[-6:]
recent_msgs = active_convo[-10:]
```

### Step 7: Add `resolve_single_clip_ref` helper

```python
def resolve_single_clip_ref(clip_ref: str, timeline_clips: list, pool_clips: list):
    """Resolve a single T/P reference to its clip data."""
    if clip_ref.startswith("T") and clip_ref[1:].isdigit():
        idx = int(clip_ref[1:])
        if idx < len(timeline_clips):
            return timeline_clips[idx]
    elif clip_ref.startswith("P") and clip_ref[1:].isdigit():
        idx = int(clip_ref[1:])
        if idx < len(pool_clips):
            return pool_clips[idx]
    return None
```

## What NOT to Change
- Don't change the pipeline, video_processor, or action detection
- Don't change the frontend (separate task)
- Don't change the proxy rendering logic
- Don't change undo/redo system
- Keep `tool_choice={"type": "tool", "name": "apply_edit"}` - same tool name, just new fields

## Testing

After implementation, test these scenarios mentally by reading the code flow:

1. **Clear instruction** ("remove last clip") -> should return mode="apply" with new timeline
2. **Ambiguous instruction** ("add salt scene" with multiple matches) -> should return mode="propose" with candidates
3. **No match** ("add the garlic roasting scene" but none exists) -> should return mode="propose" explaining nothing found
4. **User confirming** ("use P5" after a proposal) -> should return mode="apply"
5. **Undo** ("nevermind") -> should handle gracefully

## Commit
```
git add -A && git commit -m "feat: propose mode for conversational editing - discuss before ambiguous edits"
```

## Environment
- Project root: `~/.openclaw/workspace/videopeen/`
- Backend venv: `backend/.venv/`
- Do NOT restart servers - Haxx runs them manually
- Main file to edit: `backend/app/routers/edit_plan.py`
