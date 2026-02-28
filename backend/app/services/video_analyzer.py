"""Video analyzer V3: Action-based timeline analysis + AI edit decisions.

Two phases:
  Phase 1 — Action Timeline: Send batches of consecutive frames to Claude.
            Claude identifies discrete actions with precise timestamps.
  Phase 2 — Edit Decision: Send full action timeline to Claude.
            Claude acts as editor: picks clips, decides order, sets pacing.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from typing import Any

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Image encoding
# --------------------------------------------------------------------------- #

def _encode_image(path: str) -> dict:
    """Encode an image file to base64 for Claude API."""
    with open(path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    suffix = os.path.splitext(path)[1].lower()
    media_types = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_types.get(suffix, "image/jpeg"), "data": data},
    }


_OAUTH_HEADERS = {
    "anthropic-beta": "claude-code-20250219,oauth-2025-04-20",
    "user-agent": "claude-cli/1.0.0 (external, cli)",
    "x-app": "cli",
}


async def _get_user_api_key(user_email: str = "default") -> str | None:
    """Fetch user's saved API key from DB (if any)."""
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(settings.mongodb_uri)
        db = client[settings.mongodb_db]
        doc = await db.user_settings.find_one({"user_id": user_email})
        client.close()
        if doc and doc.get("api_key"):
            return doc["api_key"]
    except Exception as e:
        logger.warning("Failed to fetch user API key: %s", e)
    return None


def _build_client(key: str) -> anthropic.Anthropic:
    """Create Anthropic client from a key."""
    if key.startswith("sk-ant-oat"):
        return anthropic.Anthropic(auth_token=key, default_headers=_OAUTH_HEADERS)
    return anthropic.Anthropic(api_key=key)


def _build_async_client(key: str) -> anthropic.AsyncAnthropic:
    """Create async Anthropic client from a key."""
    if key.startswith("sk-ant-oat"):
        return anthropic.AsyncAnthropic(auth_token=key, default_headers=_OAUTH_HEADERS)
    return anthropic.AsyncAnthropic(api_key=key)


async def _resolve_api_key() -> str:
    """Resolve API key: user's saved key first, then fall back to .env."""
    user_key = await _get_user_api_key()
    if user_key:
        logger.info("Using user's saved API key")
        return user_key
    logger.info("Using .env API key")
    return settings.anthropic_api_key


def _get_client(key: str | None = None) -> anthropic.Anthropic:
    """Create Anthropic client. Pass key directly or uses .env fallback."""
    k = key or settings.anthropic_api_key
    return _build_client(k)


def _get_async_client(key: str | None = None) -> anthropic.AsyncAnthropic:
    """Create async Anthropic client. Pass key directly or uses .env fallback."""
    k = key or settings.anthropic_api_key
    return _build_async_client(k)


# --------------------------------------------------------------------------- #
# Phase 1: Action Timeline Detection
# --------------------------------------------------------------------------- #

TIMELINE_SYSTEM = """You are an expert cooking video analyst. You analyze sequences of consecutive video frames
to identify discrete cooking ACTIONS with precise timestamps.

CRITICAL RULES:
- Identify each distinct ACTION — a spice being added, stirring, flipping, pouring, plating, etc.
- Each action has a clear START and END moment
- Brief actions (1-3 seconds, like adding a spice) are JUST AS IMPORTANT as long ones
- Pay attention to what's IN THE HAND — if the hand holds a spoon with red powder, that's a specific action
- Look for TRANSITIONS: hand reaching for next ingredient = new action starting
- Pauses/idle moments (nothing happening) should be noted as "idle" actions
- Be PRECISE with timestamps based on the frame positions provided
- If an action spans across the end of this batch, note it as "continues_next: true"
"""


def _build_timeline_prompt(
    recipe_context: dict,
    frame_timestamps: list[float],
    video_name: str,
    batch_index: int,
    total_batches: int,
    prev_action_hint: str | None = None,
) -> str:
    """Build prompt for timeline detection batch."""
    steps_text = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(recipe_context.get("recipe_steps", [])))
    
    ts_text = ", ".join(f"{t:.1f}s" for t in frame_timestamps)
    
    prev_hint = ""
    if prev_action_hint:
        prev_hint = f"\nThe previous batch ended with action: \"{prev_action_hint}\". Continue from there."
    
    return f"""Analyze these {len(frame_timestamps)} consecutive frames from cooking video "{video_name}".

RECIPE: {recipe_context.get('dish_name', 'Unknown')}
STEPS:
{steps_text}

Frame timestamps: [{ts_text}]
Batch {batch_index + 1}/{total_batches} of this video.{prev_hint}

Identify every discrete ACTION in these frames. For each action:
- What exactly is happening (be specific: "adding Kashmiri chilli powder with spoon" not "seasoning")
- Which recipe step it belongs to
- Which frames show this action (by timestamp)
- Visual quality rating 1-10
- Whether it shows the ACTION happening (hand adding spice) vs the RESULT (spice already on chicken)

Return JSON:
{{
  "actions": [
    {{
      "action_id": <sequential int>,
      "description": "<specific description>",
      "recipe_step": <step number or null>,
      "start_time": <float seconds>,
      "end_time": <float seconds>,
      "action_type": "ingredient_add|mixing|cooking|plating|setup|idle|transition",
      "shows_action_moment": true/false,
      "visual_quality": <1-10>,
      "key_frame_timestamp": <timestamp of best frame for this action>,
      "continues_next": false
    }}
  ],
  "batch_summary": "<1-2 sentence summary of what happens in this batch>"
}}"""


async def detect_actions_batch(
    frame_paths: list[str],
    frame_timestamps: list[float],
    recipe_context: dict,
    video_name: str,
    batch_index: int,
    total_batches: int,
    prev_action_hint: str | None = None,
) -> dict:
    """Analyze a batch of consecutive frames to detect actions."""
    api_key = await _resolve_api_key()
    client = _get_async_client(api_key)
    
    content: list[dict] = []
    for i, (path, ts) in enumerate(zip(frame_paths, frame_timestamps)):
        content.append({"type": "text", "text": f"Frame at {ts:.1f}s:"})
        try:
            content.append(_encode_image(path))
        except Exception as e:
            logger.warning("Failed to encode %s: %s", path, e)
    
    prompt = _build_timeline_prompt(
        recipe_context, frame_timestamps, video_name,
        batch_index, total_batches, prev_action_hint,
    )
    content.append({"type": "text", "text": prompt})
    
    response = await client.messages.create(
        model=settings.vision_model,
        max_tokens=2000,
        system=TIMELINE_SYSTEM,
        messages=[{"role": "user", "content": content}],
    )
    
    text = response.content[0].text
    tokens_in = response.usage.input_tokens
    tokens_out = response.usage.output_tokens
    logger.info("Timeline batch %d/%d: %d tokens in, %d out",
                batch_index + 1, total_batches, tokens_in, tokens_out)
    
    # Parse JSON from response
    def _extract_batch_json(raw: str) -> dict:
        import re
        cleaned = re.sub(r'```json\s*', '', raw)
        cleaned = re.sub(r'```\s*', '', cleaned).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        start = cleaned.find('{')
        if start == -1:
            return {"actions": [], "batch_summary": "parse_error"}
        depth = 0
        for i in range(start, len(cleaned)):
            if cleaned[i] == '{': depth += 1
            elif cleaned[i] == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(cleaned[start:i+1])
                    except json.JSONDecodeError:
                        break
        logger.error("Failed to parse timeline response: %s", raw[:300])
        return {"actions": [], "batch_summary": "parse_error"}
    
    result = _extract_batch_json(text)
    
    return result


async def detect_actions_for_video(
    frame_paths: list[str],
    frame_timestamps: list[float],
    recipe_context: dict,
    video_name: str,
    batch_size: int = 15,
    on_batch_done: Any = None,
    max_concurrent: int = 5,
) -> list[dict]:
    """Run action detection across all frames of a video in batches.
    
    Batches run concurrently (up to max_concurrent) for faster processing.
    
    Returns merged list of actions across all batches.
    """
    n_frames = len(frame_paths)
    n_batches = max(1, (n_frames + batch_size - 1) // batch_size)
    
    semaphore = asyncio.Semaphore(max_concurrent)
    results = [None] * n_batches
    
    async def process_batch(i: int) -> None:
        async with semaphore:
            start_idx = i * batch_size
            end_idx = min(start_idx + batch_size, n_frames)
            batch_paths = frame_paths[start_idx:end_idx]
            batch_timestamps = frame_timestamps[start_idx:end_idx]
            
            result = await detect_actions_batch(
                batch_paths, batch_timestamps,
                recipe_context, video_name,
                i, n_batches, None,  # No prev_hint when parallel
            )
            results[i] = result
            
            if on_batch_done:
                actions_so_far = sum(len(r.get("actions", [])) for r in results if r)
                await on_batch_done(i + 1, n_batches, actions_so_far)
    
    await asyncio.gather(*[process_batch(i) for i in range(n_batches)])
    
    # Merge all actions
    all_actions = []
    action_id = 0
    for result in results:
        if result:
            for action in result.get("actions", []):
                action["source_video"] = video_name
                action["action_id"] = action_id
                action_id += 1
                all_actions.append(action)
    
    logger.info("Detected %d actions in %s", len(all_actions), video_name)
    return all_actions


# --------------------------------------------------------------------------- #
# Phase 2: AI Edit Decision
# --------------------------------------------------------------------------- #

EDITOR_SYSTEM = """You are a professional short-form cooking video editor specializing in ASMR/TikTok/Reels content.

You receive a complete action timeline from cooking video footage and must create a tight, punchy edit.

YOUR JOB:
- Select ONLY the most visually compelling actions
- Decide the EXACT clip order (you are the editor — you decide the narrative flow)
- Set speed for each clip (normal, fast-forward, slow-motion)
- Create a video that tells the cooking story within the TARGET DURATION

CRITICAL DURATION RULE:
- Calculate the effective duration of each clip: (end_time - start_time) / speed_factor
- Keep a RUNNING TOTAL as you add clips
- STOP adding clips when the running total reaches the target duration
- The total_effective_duration in your response MUST be within ±5 seconds of the target
- If the target is 60s, your edit must be 55-65s. NOT 80s. NOT 90s.
- FEWER clips done well > too many clips that overshoot the target
- Aim for 10-18 clips total depending on target duration

EDITING RULES:
1. EVERY ingredient addition must be shown — especially spices, sauces, pastes. Viewers want to see what goes in.
2. Prefer clips that show the ACTION MOMENT (hand adding spice) over the RESULT (spice already there)
3. Short, punchy clips: 2-4 seconds each. Max 6 seconds for hero shots.
4. Speed ramps: repetitive actions (stirring, mixing) → 2x speed. Hero moments (cheese pull, sizzle) → 0.75x slow-mo. Setup/idle → SKIP entirely.
5. Maintain chronological order within each recipe phase (prep → cook → assemble → present)
6. End with a hero shot (final presentation, cheese pull, plating reveal)
7. Each action should appear AT MOST once — no duplicates
8. If multiple videos show the same action, pick the one with better visual quality
9. Be RUTHLESS in cutting — skip anything that doesn't add value. Less is more.
10. Prefer 2-3 second clips. Only go longer for truly stunning moments."""


def _build_editor_prompt(
    recipe_context: dict,
    all_actions: list[dict],
    target_duration: float,
    video_sources: list[dict],
) -> str:
    """Build the edit decision prompt."""
    steps_text = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(recipe_context.get("recipe_steps", [])))
    
    # Format actions as compact text
    actions_text = []
    for a in all_actions:
        actions_text.append(
            f"  [{a['action_id']}] {a['start_time']:.1f}-{a['end_time']:.1f}s "
            f"| src={a.get('source_video', '?')} "
            f"| step={a.get('recipe_step', '?')} "
            f"| type={a.get('action_type', '?')} "
            f"| quality={a.get('visual_quality', '?')}/10 "
            f"| action_moment={'YES' if a.get('shows_action_moment') else 'no'} "
            f"| {a['description']}"
        )
    
    sources_text = "\n".join(
        f"  {s['name']}: {s['duration']:.1f}s ({s['n_actions']} actions)"
        for s in video_sources
    )
    
    # Track coverage
    covered_steps = set()
    for a in all_actions:
        step = a.get("recipe_step")
        if step:
            covered_steps.add(step)
    
    total_steps = len(recipe_context.get("recipe_steps", []))
    missing_steps = [i+1 for i in range(total_steps) if (i+1) not in covered_steps]
    
    max_dur = target_duration + 5
    min_dur = target_duration - 5
    
    return f"""Create an edit plan for this cooking video.

DISH: {recipe_context.get('dish_name', 'Unknown')}
TARGET DURATION: {target_duration}s (HARD LIMIT: {min_dur}-{max_dur}s. Do NOT exceed {max_dur}s.)

DURATION MATH: For each clip, effective_seconds = (end_time - start_time) / speed_factor
Keep a running total. STOP adding clips when you approach {target_duration}s.

RECIPE STEPS:
{steps_text}

VIDEO SOURCES:
{sources_text}

DETECTED ACTIONS ({len(all_actions)} total):
{chr(10).join(actions_text)}

COVERAGE: {len(covered_steps)}/{total_steps} steps detected. Missing: {missing_steps if missing_steps else 'none'}

Create the edit decision list. For each clip, specify:
- Which action (by action_id)
- Exact start_time and end_time from the source
- Speed factor
- Why you chose it

Return JSON:
{{
  "edit_plan": [
    {{
      "clip_order": 1,
      "action_id": <int>,
      "source_video": "<filename>",
      "start_time": <float>,
      "end_time": <float>,
      "speed_factor": <float: 0.75|1.0|1.5|2.0>,
      "description": "<what this clip shows>",
      "reason": "<why included>",
      "running_total": <float: cumulative effective duration after this clip>
    }}
  ],
  "total_effective_duration": <float: MUST be {min_dur}-{max_dur}s>,
  "coverage_pct": <float>,
  "missing_steps": [<step numbers not covered>],
  "editor_notes": "<brief notes about the edit>"
}}"""


async def create_edit_plan(
    recipe_context: dict,
    all_actions: list[dict],
    target_duration: float,
    video_sources: list[dict],
    best_keyframes: list[tuple[int, str]] | None = None,
) -> dict:
    """Phase 2: Claude creates the full edit plan.
    
    Args:
        recipe_context: Recipe info
        all_actions: All detected actions across videos
        target_duration: Target output duration in seconds
        video_sources: Info about each source video
        best_keyframes: Optional (action_id, frame_path) pairs for visual reference
    
    Returns:
        Edit plan dict with ordered clips
    """
    api_key = await _resolve_api_key()
    client = _get_async_client(api_key)
    
    content: list[dict] = []
    
    # Include best keyframes for visual reference (up to 15)
    if best_keyframes:
        selected_kfs = best_keyframes[:15]
        for action_id, path in selected_kfs:
            content.append({"type": "text", "text": f"Action {action_id} best frame:"})
            try:
                content.append(_encode_image(path))
            except Exception as e:
                logger.warning("Failed to encode keyframe %s: %s", path, e)
    
    prompt = _build_editor_prompt(recipe_context, all_actions, target_duration, video_sources)
    content.append({"type": "text", "text": prompt})
    
    response = await client.messages.create(
        model=settings.text_model,
        max_tokens=4000,
        system=EDITOR_SYSTEM,
        messages=[{"role": "user", "content": content}],
    )
    
    text = response.content[0].text
    tokens_in = response.usage.input_tokens
    tokens_out = response.usage.output_tokens
    logger.info("Edit plan: %d tokens in, %d out", tokens_in, tokens_out)
    
    # Parse JSON — handle markdown code blocks and extra text
    def _extract_json(raw: str) -> dict:
        """Robustly extract JSON from Claude's response."""
        # Strip markdown code fences
        import re
        cleaned = re.sub(r'```json\s*', '', raw)
        cleaned = re.sub(r'```\s*', '', cleaned).strip()
        
        # Try direct parse first
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        
        # Find the main JSON object by matching balanced braces
        start = cleaned.find('{')
        if start == -1:
            return {"edit_plan": [], "editor_notes": "parse_error"}
        
        depth = 0
        for i in range(start, len(cleaned)):
            if cleaned[i] == '{':
                depth += 1
            elif cleaned[i] == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(cleaned[start:i+1])
                    except json.JSONDecodeError:
                        break
        
        logger.error("Failed to parse edit plan: %s", raw[:500])
        return {"edit_plan": [], "editor_notes": "parse_error"}
    
    result = _extract_json(text)
    
    # Safeguard: trim clips if Claude overshoots duration
    edit_plan = result.get("edit_plan", [])
    if edit_plan:
        running = 0.0
        max_allowed = target_duration + 5
        trimmed = []
        for clip in edit_plan:
            clip_dur = (clip.get("end_time", 0) - clip.get("start_time", 0)) / clip.get("speed_factor", 1.0)
            if running + clip_dur > max_allowed and len(trimmed) >= 5:
                logger.info("Duration safeguard: trimming at %.1fs (clip %d), target was %ds", 
                           running, len(trimmed), int(target_duration))
                break
            running += clip_dur
            trimmed.append(clip)
        
        if len(trimmed) < len(edit_plan):
            logger.info("Trimmed %d clips to meet duration target (%d -> %d clips, %.1fs)", 
                        len(edit_plan) - len(trimmed), len(edit_plan), len(trimmed), running)
            result["edit_plan"] = trimmed
            result["total_effective_duration"] = running
            result["editor_notes"] = result.get("editor_notes", "") + f" [Trimmed from {len(edit_plan)} to {len(trimmed)} clips by duration safeguard]"
    
    return result


# --------------------------------------------------------------------------- #
# Legacy exports (for backward compat)
# --------------------------------------------------------------------------- #

async def analyze_scene_pass1_async(**kwargs: Any) -> dict:
    """Legacy compat — not used in V3 pipeline."""
    return {"scene_summary": {"overall_edit_value": 0}}


async def run_pass2_async(*args: Any, **kwargs: Any) -> dict:
    """Legacy compat — not used in V3 pipeline."""
    return {"coverage_check": {}}
