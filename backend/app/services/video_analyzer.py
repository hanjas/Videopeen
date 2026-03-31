"""Video analyzer V3/V7: Action-based timeline analysis + AI edit decisions.

V3 (legacy): Send batches of consecutive frames to Claude Vision.
V7 (current): Send compressed video directly to Gemini for analysis.

Phase 1 — Action Timeline: Gemini analyzes full video (V7) or frame batches (V3).
Phase 2 — Edit Decision: Claude acts as editor (unchanged).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import subprocess
import time
import urllib.request
import urllib.error
from typing import Any

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# API Retry Wrapper
# --------------------------------------------------------------------------- #

async def _call_claude_with_retry(client, **kwargs):
    """Call Claude API with exponential backoff retry."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return await client.messages.create(**kwargs)
        except Exception as e:
            error_str = str(e)
            is_retryable = any(code in error_str for code in ["529", "529", "rate_limit", "overloaded"])
            if hasattr(e, 'status_code'):
                is_retryable = is_retryable or e.status_code in [429, 500, 502, 503, 529]
            
            if is_retryable and attempt < max_retries - 1:
                wait_time = (2 ** attempt) + (attempt * 0.5)  # 1s, 2.5s, 5s
                logger.warning("API call failed (attempt %d/%d), retrying in %.1fs: %s", 
                              attempt + 1, max_retries, wait_time, str(e)[:100])
                await asyncio.sleep(wait_time)
            else:
                raise


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
# Gemini Direct Video Analysis (V7)
# --------------------------------------------------------------------------- #

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com"


def _gemini_api_request(url: str, data: dict | None = None, headers: dict | None = None, method: str | None = None) -> tuple[int, dict, dict]:
    """Simple urllib wrapper for Gemini API calls."""
    headers = headers or {}
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return resp.status, json.loads(resp.read()), dict(resp.headers)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        return e.code, {"error": error_body[:500]}, {}


async def compress_video_for_gemini(
    video_path: str,
    output_path: str,
    resolution: int = 720,
    fps: int = 30,
    crf: int = 28,
    max_size_mb: int = 50,
) -> str:
    """Compress video for Gemini upload using ffmpeg.
    
    Args:
        video_path: Source video path
        output_path: Compressed output path  
        resolution: Target height (720p default)
        fps: Target framerate
        crf: Quality factor (higher = smaller, 28 is good balance)
        max_size_mb: Max file size in MB
    
    Returns:
        Path to compressed video
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"scale=-2:{resolution}",
        "-r", str(fps),
        "-c:v", "libx264",
        "-crf", str(crf),
        "-preset", "fast",
        "-c:a", "aac",
        "-b:a", "64k",
        output_path,
    ]
    
    start = time.time()
    result = await asyncio.to_thread(
        subprocess.run, cmd, capture_output=True, text=True, timeout=300
    )
    
    if result.returncode != 0:
        raise RuntimeError(f"Video compression failed: {result.stderr[-300:]}")
    
    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    elapsed = time.time() - start
    logger.info("Compressed %s → %.1f MB in %.1fs", os.path.basename(video_path), size_mb, elapsed)
    
    if size_mb > max_size_mb:
        # Re-compress with higher CRF
        logger.warning("Compressed file %.1f MB > %d MB limit, re-compressing with CRF %d", 
                       size_mb, max_size_mb, crf + 5)
        cmd[cmd.index(str(crf))] = str(crf + 5)
        result = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0:
            raise RuntimeError(f"Re-compression failed: {result.stderr[-300:]}")
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.info("Re-compressed to %.1f MB", size_mb)
    
    return output_path


async def upload_to_gemini(video_path: str, api_key: str) -> tuple[str, str]:
    """Upload video to Gemini Files API using resumable upload.
    
    Args:
        video_path: Path to compressed video
        api_key: Gemini API key
    
    Returns:
        Tuple of (file_uri, file_name) for use in generateContent
    """
    file_size = os.path.getsize(video_path)
    display_name = os.path.basename(video_path).replace(" ", "_")
    
    start = time.time()
    
    # Initiate resumable upload
    init_req = urllib.request.Request(
        f"{GEMINI_BASE_URL}/upload/v1beta/files?key={api_key}",
        data=json.dumps({"file": {"display_name": display_name}}).encode(),
        headers={
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(file_size),
            "X-Goog-Upload-Header-Content-Type": "video/mp4",
            "Content-Type": "application/json",
        },
    )
    
    with urllib.request.urlopen(init_req) as resp:
        upload_url = resp.headers.get("X-Goog-Upload-URL")
        if not upload_url:
            raise RuntimeError("Gemini Files API did not return upload URL")
    
    # Upload file data
    with open(video_path, "rb") as f:
        file_data = f.read()
    
    upload_req = urllib.request.Request(
        upload_url,
        data=file_data,
        headers={
            "X-Goog-Upload-Command": "upload, finalize",
            "X-Goog-Upload-Offset": "0",
            "Content-Length": str(len(file_data)),
        },
    )
    
    with urllib.request.urlopen(upload_req, timeout=120) as resp:
        upload_result = json.loads(resp.read())
    
    file_uri = upload_result.get("file", {}).get("uri")
    file_name = upload_result.get("file", {}).get("name")
    
    elapsed = time.time() - start
    logger.info("Uploaded %s (%.1f MB) to Gemini in %.1fs → %s", 
                display_name, file_size / (1024 * 1024), elapsed, file_uri)
    
    # Wait for processing
    wait_start = time.time()
    while True:
        status_code, resp_data, _ = await asyncio.to_thread(
            _gemini_api_request,
            f"{GEMINI_BASE_URL}/v1beta/{file_name}?key={api_key}",
        )
        state = resp_data.get("state", "UNKNOWN")
        if state == "ACTIVE":
            logger.info("Gemini file processing complete (%.1fs)", time.time() - wait_start)
            break
        elif state == "FAILED":
            raise RuntimeError(f"Gemini file processing failed: {resp_data}")
        else:
            logger.debug("Gemini file state: %s, waiting...", state)
            await asyncio.sleep(3)
        
        if time.time() - wait_start > 120:
            raise RuntimeError("Gemini file processing timed out (>120s)")
    
    return file_uri, file_name


async def cleanup_gemini_file(file_name: str, api_key: str) -> None:
    """Delete uploaded file from Gemini Files API."""
    try:
        await asyncio.to_thread(
            _gemini_api_request,
            f"{GEMINI_BASE_URL}/v1beta/{file_name}?key={api_key}",
            method="DELETE",
        )
        logger.info("Cleaned up Gemini file: %s", file_name)
    except Exception as e:
        logger.warning("Failed to cleanup Gemini file %s: %s", file_name, e)


GEMINI_TIMELINE_PROMPT = """You are an expert cooking video analyst. Watch this entire cooking video carefully and identify every distinct cooking action/step with precise timestamps.

RECIPE: {dish_name}
RECIPE STEPS:
{recipe_steps}

VIDEO: "{video_name}" ({duration:.1f} seconds)

CRITICAL RULES:
1. Identify EVERY discrete ACTION — a spice being added, stirring, flipping, pouring, plating, etc.
2. Each action must have precise START and END timestamps (in seconds, float)
3. Brief actions (1-3 seconds, like adding a spice) are JUST AS IMPORTANT as long ones
4. Pay attention to what's IN THE HAND — if the hand holds a spoon with red powder, that's a specific action
5. Look for TRANSITIONS: hand reaching for next ingredient = new action starting  
6. Note AUDIO CUES: sizzling, chopping sounds, bubbling, speech
7. Track COOKING STATE CHANGES: raw → cooked, solid → melted, cold → bubbling
8. Pauses/idle moments (nothing happening) should be noted as "idle" actions
9. If ingredients appear that you didn't see being added, mark as "inferred_addition"
10. Match actions to recipe steps where possible

For each action provide:
- action_id (sequential integer starting from 0)
- description (specific: "adding Kashmiri chilli powder with spoon" not just "seasoning")
- recipe_step (step number from recipe, or null if unclear)
- start_time (float, seconds)
- end_time (float, seconds)  
- action_type: one of "ingredient_add", "mixing", "cooking", "cutting", "plating", "setup", "idle", "transition", "inferred_addition", "presentation"
- shows_action_moment: true if the clip shows the action happening (hand adding spice) vs just the result
- visual_quality: 1-10 rating
- audio_cues: any relevant sounds detected (or null)
- key_frame_timestamp: timestamp of the single best frame representing this action

Return ONLY valid JSON (no markdown, no explanation):
{{
  "actions": [
    {{
      "action_id": 0,
      "description": "...",
      "recipe_step": null,
      "start_time": 0.0,
      "end_time": 0.0,
      "action_type": "...",
      "shows_action_moment": true,
      "visual_quality": 8,
      "audio_cues": "sizzling" or null,
      "key_frame_timestamp": 0.0
    }}
  ],
  "video_summary": "brief summary of the full video",
  "total_actions": 0,
  "detected_ingredients": ["list of ingredients seen"],
  "missing_ingredients": ["recipe ingredients NOT observed"]
}}"""


async def detect_actions_gemini(
    video_path: str,
    recipe_context: dict,
    video_name: str,
    video_duration: float,
    api_key: str | None = None,
    gemini_api_key: str | None = None,
    on_progress: Any = None,
) -> list[dict]:
    """Detect cooking actions using Gemini direct video analysis (V7).
    
    Compresses the video, uploads to Gemini Files API, and analyzes in a single call.
    
    Args:
        video_path: Path to source video file
        recipe_context: Recipe info dict with dish_name and recipe_steps
        video_name: Display name for the video
        video_duration: Duration in seconds
        api_key: Claude API key (unused, kept for interface compat)
        gemini_api_key: Gemini API key
        on_progress: Optional async callback(step: str, progress: float)
    
    Returns:
        List of action dicts compatible with existing pipeline
    """
    g_key = gemini_api_key or settings.gemini_api_key
    if not g_key:
        raise ValueError("GEMINI_API_KEY not configured. Set it in .env")
    
    model = settings.gemini_model
    
    # Step 1: Compress video
    if on_progress:
        await on_progress("Compressing video for analysis...", 0.1)
    
    compressed_dir = os.path.join(os.path.dirname(video_path), ".gemini_temp")
    os.makedirs(compressed_dir, exist_ok=True)
    compressed_path = os.path.join(compressed_dir, f"{os.path.splitext(video_name)[0]}_compressed.mp4")
    
    await compress_video_for_gemini(
        video_path, compressed_path,
        resolution=settings.gemini_compress_resolution,
        fps=settings.gemini_compress_fps,
        crf=settings.gemini_compress_crf,
    )
    
    # Step 2: Upload to Gemini
    if on_progress:
        await on_progress("Uploading to Gemini...", 0.3)
    
    file_uri, file_name = await upload_to_gemini(compressed_path, g_key)
    
    try:
        # Step 3: Analyze with Gemini
        if on_progress:
            await on_progress("Gemini analyzing video...", 0.5)
        
        steps_text = "\n".join(
            f"  {i+1}. {s}" for i, s in enumerate(recipe_context.get("recipe_steps", []))
        ) or "  (No recipe steps provided)"
        
        prompt = GEMINI_TIMELINE_PROMPT.format(
            dish_name=recipe_context.get("dish_name", "Unknown"),
            recipe_steps=steps_text,
            video_name=video_name,
            duration=video_duration,
        )
        
        start = time.time()
        status_code, result, _ = await asyncio.to_thread(
            _gemini_api_request,
            f"{GEMINI_BASE_URL}/v1beta/models/{model}:generateContent?key={g_key}",
            data={
                "contents": [{
                    "parts": [
                        {"file_data": {"mime_type": "video/mp4", "file_uri": file_uri}},
                        {"text": prompt},
                    ]
                }],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": 8192,
                    "responseMimeType": "application/json",
                },
            },
        )
        
        analysis_time = time.time() - start
        
        if "candidates" not in result:
            error_msg = json.dumps(result)[:500]
            raise RuntimeError(f"Gemini API error: {error_msg}")
        
        # Parse response
        response_text = result["candidates"][0]["content"]["parts"][0]["text"]
        usage = result.get("usageMetadata", {})
        
        logger.info(
            "Gemini video analysis complete: %.1fs, %d prompt tokens, %d output tokens, %d thinking tokens",
            analysis_time,
            usage.get("promptTokenCount", 0),
            usage.get("candidatesTokenCount", 0),
            usage.get("thoughtsTokenCount", 0),
        )
        
        # Parse JSON
        try:
            parsed = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON from response
            import re
            cleaned = re.sub(r'```json\s*', '', response_text)
            cleaned = re.sub(r'```\s*', '', cleaned).strip()
            start_idx = cleaned.find('{')
            if start_idx == -1:
                raise RuntimeError(f"Failed to parse Gemini response: {response_text[:300]}")
            depth = 0
            for i in range(start_idx, len(cleaned)):
                if cleaned[i] == '{': depth += 1
                elif cleaned[i] == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            parsed = json.loads(cleaned[start_idx:i+1])
                            break
                        except json.JSONDecodeError:
                            continue
            else:
                raise RuntimeError(f"Failed to parse Gemini response JSON: {response_text[:300]}")
        
        actions = parsed.get("actions", [])
        
        # Normalize action format for pipeline compatibility
        for action in actions:
            action["source_video"] = video_name
            # Ensure required fields
            action.setdefault("shows_action_moment", True)
            action.setdefault("visual_quality", 5)
            action.setdefault("key_frame_timestamp", action.get("start_time", 0))
            action.setdefault("recipe_step", None)
            action.setdefault("action_type", "cooking")
            
            # Fix zero-duration actions
            if action.get("end_time", 0) <= action.get("start_time", 0):
                mid = action.get("start_time", 0)
                action["start_time"] = max(0, mid - 1.0)
                action["end_time"] = mid + 1.0
        
        if on_progress:
            await on_progress(f"Detected {len(actions)} actions", 0.9)
        
        logger.info("Gemini detected %d actions in %s (%.1fs video, %.1fs analysis)",
                     len(actions), video_name, video_duration, analysis_time)
        
        return actions
    
    finally:
        # Cleanup: delete from Gemini and local compressed file
        await cleanup_gemini_file(file_name, g_key)
        try:
            os.remove(compressed_path)
            # Remove temp dir if empty
            if not os.listdir(compressed_dir):
                os.rmdir(compressed_dir)
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# Phase 1: Action Timeline Detection (Legacy Claude Vision - V3)
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

STATE-DIFF RULE:
- When marking a period as IDLE, compare the scene at the START vs END of the idle period.
- If ANY new ingredient, substance, powder, liquid, or item has appeared that wasn't there before,
  mark it as an ACTION with action_type "inferred_addition" and description
  "[item] appeared — likely added between Xs-Ys" even if you didn't see the hand movement.
- A 40-second "idle" gap in a spice-adding sequence is suspicious — look carefully for changes.
- If the bowl/pot has new content compared to the previous frames, SOMETHING was added.
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
    
    overlap_note = ""
    if batch_index > 0:
        overlap_note = "\nNote: The first frame of this batch overlaps with the last frame of the previous batch for context continuity."
    
    return f"""Analyze these {len(frame_timestamps)} consecutive frames from cooking video "{video_name}".

RECIPE: {recipe_context.get('dish_name', 'Unknown')}
STEPS:
{steps_text}

INGREDIENT TRACKING:
The recipe steps above mention specific ingredients. Use them to help identify what you see:
- Match powder colors to expected spices (brown = garam masala/cumin, yellow = turmeric, red/orange = chili, white = salt/sugar/flour)
- If you see fewer ingredient additions than the recipe expects, note which ones were NOT observed
- Add a "missing_ingredients" field to your response listing expected but undetected ingredients

Frame timestamps: [{ts_text}]
Batch {batch_index + 1}/{total_batches} of this video.{overlap_note}{prev_hint}

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
      "action_type": "ingredient_add|mixing|cooking|plating|setup|idle|transition|inferred_addition",
      "shows_action_moment": true/false,
      "visual_quality": <1-10>,
      "key_frame_timestamp": <timestamp of best frame for this action>,
      "continues_next": false
    }}
  ],
  "batch_summary": "<1-2 sentence summary of what happens in this batch>",
  "missing_ingredients": ["list of recipe ingredients not observed in this batch"]
}}"""


async def detect_actions_batch(
    frame_paths: list[str],
    frame_timestamps: list[float],
    recipe_context: dict,
    video_name: str,
    batch_index: int,
    total_batches: int,
    prev_action_hint: str | None = None,
    api_key: str | None = None,
) -> dict:
    """Analyze a batch of consecutive frames to detect actions."""
    key = api_key or await _resolve_api_key()
    client = _get_async_client(key)
    
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
    
    response = await _call_claude_with_retry(
        client,
        model=settings.fast_vision_model,
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
    
    # Retry once if parse failed
    if result.get("batch_summary") == "parse_error":
        logger.warning("Parse error on batch %d, retrying...", batch_index + 1)
        response = await _call_claude_with_retry(
            client,
            model=settings.fast_vision_model,
            max_tokens=2000,
            system=TIMELINE_SYSTEM,
            messages=[{"role": "user", "content": content}],
        )
        text = response.content[0].text
        result = _extract_batch_json(text)
        if result.get("batch_summary") == "parse_error":
            logger.error("Parse error on retry for batch %d, giving up", batch_index + 1)
    
    return result


def _dedup_actions(actions: list[dict], overlap_threshold: float = 0.7, merge_gap: float = 0.3) -> list[dict]:
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
            
            elif overlap_ratio > 0 or (b_start - a_end) < merge_gap:
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


async def detect_actions_for_video(
    frame_paths: list[str],
    frame_timestamps: list[float],
    recipe_context: dict,
    video_name: str,
    batch_size: int = 15,
    on_batch_done: Any = None,
    max_concurrent: int = 5,
    shared_semaphore: asyncio.Semaphore | None = None,
    api_key: str | None = None,
) -> list[dict]:
    """Run action detection across all frames of a video in batches.
    
    Batches run concurrently (up to max_concurrent) for faster processing.
    When shared_semaphore is provided, it's used instead of creating a per-video one.
    This allows a global concurrency cap across multiple videos.
    
    Returns merged list of actions across all batches.
    """
    n_frames = len(frame_paths)
    n_batches = max(1, (n_frames + batch_size - 1) // batch_size)
    
    semaphore = shared_semaphore or asyncio.Semaphore(max_concurrent)
    results = [None] * n_batches
    
    async def process_batch(i: int) -> None:
        async with semaphore:
            start_idx = i * batch_size
            if i > 0:
                start_idx -= 1  # Include last frame of previous batch
            end_idx = min((i + 1) * batch_size, n_frames)
            batch_paths = frame_paths[start_idx:end_idx]
            batch_timestamps = frame_timestamps[start_idx:end_idx]
            
            result = await detect_actions_batch(
                batch_paths, batch_timestamps,
                recipe_context, video_name,
                i, n_batches, None,  # No prev_hint when parallel
                api_key=api_key,
            )
            results[i] = result
            
            if on_batch_done:
                actions_so_far = sum(len(r.get("actions", [])) for r in results if r)
                await on_batch_done(i + 1, n_batches, actions_so_far)
    
    await asyncio.gather(*[process_batch(i) for i in range(n_batches)])
    
    # Merge all actions, fix zero-duration clips
    all_actions = []
    action_id = 0
    zero_dur_fixed = 0
    for result in results:
        if result:
            for action in result.get("actions", []):
                action["source_video"] = video_name
                start = action.get("start_time", 0)
                end = action.get("end_time", 0)
                # Fix zero-duration actions: expand to at least 2 seconds
                if end <= start:
                    mid = start
                    action["start_time"] = max(0, mid - 1.0)
                    action["end_time"] = mid + 1.0
                    zero_dur_fixed += 1
                action["action_id"] = action_id
                action_id += 1
                all_actions.append(action)
    
    if zero_dur_fixed:
        logger.info("Fixed %d zero-duration actions (expanded to 2s) in %s", zero_dur_fixed, video_name)
    logger.info("Detected %d actions in %s", len(all_actions), video_name)
    
    # Deduplicate overlapping/fragmented actions from parallel batch processing
    if settings.dedup_enabled:
        all_actions = _dedup_actions(
            all_actions,
            overlap_threshold=settings.dedup_overlap_threshold,
            merge_gap=settings.dedup_merge_gap,
        )
        logger.info("After dedup: %d actions in %s", len(all_actions), video_name)
    else:
        logger.info("Dedup disabled, keeping all %d actions in %s", len(all_actions), video_name)
    
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

CRITICAL DURATION RULE (THIS IS YOUR #1 PRIORITY):
- Calculate the effective duration of each clip: (end_time - start_time) / speed_factor
- Keep a RUNNING TOTAL as you add clips
- STOP adding clips when the running total reaches the target duration
- The total_effective_duration in your response MUST be within ±5 seconds of the target
- If the target is 90s, your edit MUST be 85-95s. If 120s, MUST be 115-125s. Match the target!
- Do NOT default to 60s. The target duration is explicitly given - FOLLOW IT.
- For longer targets (>60s): use MORE clips, use LONGER clips (3-5s instead of 2-3s), include more recipe steps, add more hero/beauty shots, use more slow-mo
- Estimate clips needed: target_duration / 3.5 = approximate clip count
- VERIFY your total before responding. If under target, ADD MORE CLIPS.

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
TARGET DURATION: {target_duration}s (HARD LIMIT: {min_dur}-{max_dur}s. Do NOT go below {min_dur}s or exceed {max_dur}s.)
ESTIMATED CLIPS NEEDED: ~{int(target_duration / 3.5)} clips

DURATION MATH: For each clip, effective_seconds = (end_time - start_time) / speed_factor
Keep a running total. STOP adding clips when you approach {target_duration}s.
WARNING: Do NOT default to 60s. Your target is {target_duration}s. If your total is under {min_dur}s, you MUST add more clips.

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
    api_key: str | None = None,
) -> dict:
    """Phase 2: Claude creates the full edit plan.
    
    Args:
        recipe_context: Recipe info
        all_actions: All detected actions across videos
        target_duration: Target output duration in seconds
        video_sources: Info about each source video
        best_keyframes: Optional (action_id, frame_path) pairs for visual reference
        api_key: Optional API key (avoids repeated DB lookups)
    
    Returns:
        Edit plan dict with ordered clips
    """
    key = api_key or await _resolve_api_key()
    client = _get_async_client(key)
    
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
    
    response = await _call_claude_with_retry(
        client,
        model=settings.text_model,
        max_tokens=16000,
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
