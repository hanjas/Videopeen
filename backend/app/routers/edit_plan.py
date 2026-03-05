"""Edit plan endpoints — review, reorder, confirm & render."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.models.project import ProjectStatus
from app.services.render import render_from_edit_plan
from app.services.video_analyzer import _resolve_api_key, _build_async_client
from app.services.proxy_renderer import (
    pre_render_proxy_clips,
    fast_concat_proxies,
    get_existing_proxies,
    identify_new_clips,
)
from app.services.text_overlay import auto_generate_overlays_from_recipe
from app.services.thumbnail import generate_thumbnails_from_clips
from app.services.clip_finder import find_clips_by_text, smart_find_clip
from app.websocket.manager import ws_manager
from app.config import settings

logger = logging.getLogger(__name__)

REFINE_SYSTEM_PROMPT = """You are the video editor inside Videopeen, a cooking video editor. You re-edit short-form cooking videos based on user instructions.

COOKING VIDEO RULES:
- Every video needs: hook (0-3s), process highlights, money shot (plated result at the end)
- Never cut mid-action (mid-pour, mid-flip). Cut on completed actions.
- Sizzle/steam/close-up shots are high-value. Prefer them over wide static shots.
- Maintain chronological cooking order unless user explicitly asks otherwise.
- Speed up: chopping, stirring, waiting, kneading. Never speed up: plating, sauce pours, reveals, drizzles.
- Favor transformation moments: raw to cooked, separate to combined, plain to garnished.
- Close-ups > wide shots for short-form content.

EDITING RULES:
- Stay within target_duration ±5 seconds.
- Prefer clips with higher quality scores.
- When removing clips, close the gap.
- When adding clips from the pool, place them in chronological cooking order.
- Prefer minimal changes — don't reshuffle the whole timeline unless explicitly asked.
- If an instruction is vague ("make it better"), tighten pacing and ensure money shot is strong.
- If an instruction is impossible, explain why in summary and return the best valid timeline.

TERMINOLOGY YOU UNDERSTAND:
- "money shot" / "hero shot" = final plated dish
- "the sizzle" = food hitting hot oil close-up
- "the pour" / "the drizzle" = liquid being added
- "the pull" / "cheese pull" = stretchy revealing moment
- "mise en place" / "the prep" = ingredients laid out
- "punchier" / "snappy" = faster cuts, remove pauses
- "more satisfying" / "ASMR" = more sizzle, pour, crunch moments
- "TikTok style" = hook first, fast cuts
- "the ugly parts" = bad lighting, messy counter
- "boring part" = low-action footage

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

CRITICAL RULE - CLIPS ARRAY:
When using mode="apply", you MUST ALWAYS include the COMPLETE clips array with ALL timeline clips.
Even if the user says "ok", "proceed", "looks good", "confirm" — you must return the full current timeline in the clips array.
If no changes are needed, return all current T-clips exactly as they are.
NEVER return mode="apply" with an empty clips array. That will break the system."""

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

router = APIRouter(prefix="/api/projects/{project_id}/edit-plan", tags=["edit-plan"])


def _db(request: Request):
    return request.app.state.db


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


def should_trigger_smart_search(result: dict, mode: str) -> bool:
    """Detect if Claude's response indicates it couldn't find a clip."""
    summary = result.get("summary", "").lower()
    
    # Mode is "propose" AND candidates list is empty or all have low relevance
    if mode == "propose":
        candidates = result.get("candidates", [])
        if not candidates:
            return True
        # Check if all candidates have very low relevance scores
        low_relevance_count = sum(1 for c in candidates if c.get("relevance", 0) < 0.4)
        if low_relevance_count == len(candidates):
            return True
    
    # Mode is "apply" but summary mentions "couldn't find" / "no matching clip"
    not_found_phrases = [
        "couldn't find",
        "can't find",
        "unable to find",
        "no matching clip",
        "not in the pool",
        "don't see",
        "doesn't appear",
        "not available",
        "no clip for",
    ]
    if any(phrase in summary for phrase in not_found_phrases):
        return True
    
    # Mode is "propose" and summary contains uncertainty language
    if mode == "propose":
        uncertainty_phrases = [
            "not sure which",
            "unclear which",
            "might be",
            "could be",
            "possibly",
            "unclear if",
        ]
        if any(phrase in summary for phrase in uncertainty_phrases):
            # Only trigger if also mentions searching/finding
            if any(word in summary for word in ["find", "search", "looking for", "locate"]):
                return True
    
    return False


# ---- Models ---- #

class UpdateClipsRequest(BaseModel):
    """Update the clip order/selection."""
    clips: list[dict[str, Any]]  # Full clips array with new order


class ConfirmRequest(BaseModel):
    """Confirm edit plan and start render."""
    pass


class RefineRequest(BaseModel):
    """Conversational edit instruction."""
    instruction: str


class SmartSearchRequest(BaseModel):
    """Manual smart clip search request."""
    query: str


class TextOverlay(BaseModel):
    """Text overlay configuration."""
    text: str
    start_time: float
    end_time: float
    position: str = "bottom-center"  # top-left, top-center, bottom-center, center
    style: str = "bold-white"  # bold-white, subtitle-bar, minimal
    font_size: int = 48


class UpdateOverlaysRequest(BaseModel):
    """Update text overlays."""
    overlays: list[TextOverlay]


class AutoGenerateOverlaysRequest(BaseModel):
    """Auto-generate overlays from recipe steps."""
    style: str = "bold-white"


# ---- Endpoints ---- #

@router.get("")
async def get_edit_plan(project_id: str, request: Request):
    """Get the current edit plan for a project."""
    db = _db(request)
    plan = await db.edit_plans.find_one({"project_id": project_id})
    if not plan:
        raise HTTPException(404, "No edit plan found. Process the project first.")
    return plan


@router.get("/conversation")
async def get_conversation(project_id: str, request: Request):
    """Get the conversation history for a project."""
    db = _db(request)
    plan = await db.edit_plans.find_one(
        {"project_id": project_id},
        {"conversation": 1, "version": 1}
    )
    if not plan:
        raise HTTPException(404, "No edit plan found")
    return {
        "conversation": plan.get("conversation", []),
        "current_version": plan.get("version", 1)
    }


@router.patch("")
async def update_edit_plan(project_id: str, body: UpdateClipsRequest, request: Request):
    """Update clip order/selection. Only allowed in draft status."""
    db = _db(request)
    plan = await db.edit_plans.find_one({"project_id": project_id})
    if not plan:
        raise HTTPException(404, "No edit plan found")
    
    if plan.get("status") not in ("draft",):
        raise HTTPException(409, "Edit plan is not in draft status")

    # Recalculate effective durations and order
    new_clips = body.clips
    for i, clip in enumerate(new_clips):
        clip["order"] = i
        duration = clip.get("end_time", 0) - clip.get("start_time", 0)
        clip["duration"] = duration
        clip["effective_duration"] = duration / clip.get("speed_factor", 1.0)

    total_effective = sum(c["effective_duration"] for c in new_clips if c.get("status") == "included")

    # Bump version
    new_version = plan.get("version", 1) + 1
    history_entry = {
        "version": new_version,
        "source": "user",
        "action": "update_clips",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    await db.edit_plans.update_one(
        {"project_id": project_id},
        {
            "$set": {
                "timeline.clips": new_clips,
                "timeline.total_effective_duration": total_effective,
                "version": new_version,
                "status": "draft",
            },
            "$push": {"history": history_entry},
        },
    )

    # Also update edit_decisions for backward compat
    await db.edit_decisions.delete_many({"project_id": project_id})
    for clip in new_clips:
        if clip.get("status") != "included":
            continue
        doc = {
            "project_id": project_id,
            "sequence_order": clip["order"],
            "action_id": clip.get("action_id"),
            "source_path": clip.get("source_path", ""),
            "start_time": clip["start_time"],
            "end_time": clip["end_time"],
            "duration": clip["duration"],
            "speed_factor": clip.get("speed_factor", 1.0),
            "description": clip.get("description", ""),
            "reason": clip.get("reason", ""),
            "filename": clip.get("source_video", ""),
        }
        await db.edit_decisions.insert_one(doc)

    return {"success": True, "version": new_version, "total_effective_duration": total_effective}


@router.post("/confirm")
async def confirm_and_render(project_id: str, request: Request):
    """Confirm the edit plan and start rendering."""
    db = _db(request)
    plan = await db.edit_plans.find_one({"project_id": project_id})
    if not plan:
        raise HTTPException(404, "No edit plan found")
    
    if plan.get("status") not in ("draft",):
        raise HTTPException(409, f"Edit plan status is '{plan.get('status')}', expected 'draft'")

    # Lock the plan
    await db.edit_plans.update_one(
        {"project_id": project_id},
        {"$set": {"status": "confirmed"}},
    )

    # Start render in background
    asyncio.create_task(render_from_edit_plan(db, project_id))

    return {"message": "Render started", "project_id": project_id}


@router.get("/thumbnails/{clip_id}")
async def get_clip_thumbnail(project_id: str, clip_id: str, request: Request):
    """Serve thumbnail for a specific clip."""
    db = _db(request)
    plan = await db.edit_plans.find_one({"project_id": project_id})
    if not plan:
        raise HTTPException(404, "No edit plan found")

    # Search in timeline clips and clip pool
    all_clips = plan.get("timeline", {}).get("clips", []) + plan.get("clip_pool", [])
    clip = next((c for c in all_clips if c.get("clip_id") == clip_id), None)
    if not clip:
        raise HTTPException(404, "Clip not found")

    thumb_path = clip.get("thumbnail_path")
    if not thumb_path or not os.path.exists(thumb_path):
        raise HTTPException(404, "Thumbnail not available")

    return FileResponse(thumb_path, media_type="image/jpeg")


@router.get("/preview")
async def get_proxy_preview(project_id: str, request: Request):
    """Serve the proxy preview video."""
    db = _db(request)
    plan = await db.edit_plans.find_one({"project_id": project_id})
    if not plan:
        raise HTTPException(404, "No edit plan found")
    
    proxy_path = plan.get("proxy_preview_path")
    if not proxy_path or not os.path.exists(proxy_path):
        raise HTTPException(404, "Proxy preview not available")
    
    return FileResponse(proxy_path, media_type="video/mp4")


# ---- Text Overlay Endpoints ---- #

@router.get("/overlays")
async def get_text_overlays(project_id: str, request: Request):
    """Get current text overlays for the project."""
    db = _db(request)
    plan = await db.edit_plans.find_one({"project_id": project_id})
    if not plan:
        raise HTTPException(404, "No edit plan found")
    
    overlays = plan.get("text_overlays", [])
    return {"overlays": overlays, "count": len(overlays)}


@router.post("/overlays")
async def update_text_overlays(
    project_id: str,
    body: UpdateOverlaysRequest,
    request: Request,
):
    """Update text overlays for the project."""
    db = _db(request)
    plan = await db.edit_plans.find_one({"project_id": project_id})
    if not plan:
        raise HTTPException(404, "No edit plan found")
    
    # Convert Pydantic models to dicts
    overlays_data = [overlay.model_dump() for overlay in body.overlays]
    
    # Validate overlay time ranges
    for overlay in overlays_data:
        if overlay["end_time"] <= overlay["start_time"]:
            raise HTTPException(
                400,
                f"Invalid time range for overlay '{overlay['text']}': "
                f"end_time must be greater than start_time"
            )
    
    # Update edit plan with overlays
    await db.edit_plans.update_one(
        {"project_id": project_id},
        {"$set": {"text_overlays": overlays_data}},
    )
    
    logger.info("Updated text overlays for project %s: %d overlays", project_id, len(overlays_data))
    
    return {
        "success": True,
        "overlays": overlays_data,
        "count": len(overlays_data),
    }


@router.post("/overlays/auto-generate")
async def auto_generate_text_overlays(
    project_id: str,
    body: AutoGenerateOverlaysRequest,
    request: Request,
):
    """Auto-generate text overlays from recipe steps."""
    db = _db(request)
    
    # Get project and edit plan
    project = await db.projects.find_one({"_id": project_id})
    if not project:
        raise HTTPException(404, "Project not found")
    
    plan = await db.edit_plans.find_one({"project_id": project_id})
    if not plan:
        raise HTTPException(404, "No edit plan found")
    
    # Get recipe steps from project (could be in different fields)
    recipe_steps = []
    
    # Try to extract recipe steps from instructions
    instructions = project.get("instructions", "")
    if instructions:
        # Simple extraction: split by newlines and filter out empty lines
        recipe_steps = [
            step.strip()
            for step in instructions.split("\n")
            if step.strip() and not step.strip().startswith("#")
        ]
    
    # Fallback: use recipe_details if instructions is empty
    if not recipe_steps:
        recipe_details = project.get("recipe_details", "")
        if recipe_details:
            recipe_steps = [
                step.strip()
                for step in recipe_details.split("\n")
                if step.strip()
            ]
    
    if not recipe_steps:
        raise HTTPException(
            400,
            "No recipe steps found in project. "
            "Add recipe steps to project instructions or recipe_details first."
        )
    
    # Get timeline clips
    timeline_clips = plan.get("timeline", {}).get("clips", [])
    included_clips = [c for c in timeline_clips if c.get("status") == "included"]
    
    if not included_clips:
        raise HTTPException(400, "No clips in timeline to generate overlays for")
    
    # Auto-generate overlays
    overlays_data = auto_generate_overlays_from_recipe(
        recipe_steps=recipe_steps,
        clips=included_clips,
        style=body.style,
    )
    
    if not overlays_data:
        raise HTTPException(500, "Failed to generate overlays")
    
    # Save to edit plan
    await db.edit_plans.update_one(
        {"project_id": project_id},
        {"$set": {"text_overlays": overlays_data}},
    )
    
    logger.info(
        "Auto-generated %d text overlays for project %s from %d recipe steps",
        len(overlays_data),
        project_id,
        len(recipe_steps),
    )
    
    return {
        "success": True,
        "overlays": overlays_data,
        "count": len(overlays_data),
        "recipe_steps_count": len(recipe_steps),
    }


@router.get("/thumbnails")
async def get_thumbnails(project_id: str, request: Request):
    """Get top 3 thumbnail images for the project.
    
    Returns thumbnail URLs based on highest visual quality clips.
    Generates thumbnails on-demand if not already created.
    """
    db = _db(request)
    
    # Get edit plan
    plan = await db.edit_plans.find_one({"project_id": project_id})
    if not plan:
        raise HTTPException(404, "No edit plan found")
    
    # Combine timeline clips + clip pool for thumbnail selection
    timeline_clips = plan.get("timeline", {}).get("clips", [])
    clip_pool = plan.get("clip_pool", [])
    all_clips = timeline_clips + clip_pool
    
    if not all_clips:
        raise HTTPException(404, "No clips available for thumbnail generation")
    
    # Generate thumbnails directory
    thumbnails_dir = os.path.join(settings.output_dir, "thumbnails")
    os.makedirs(thumbnails_dir, exist_ok=True)
    
    # Generate top 3 thumbnails
    thumbnails = await asyncio.to_thread(
        generate_thumbnails_from_clips,
        clips=all_clips,
        output_dir=thumbnails_dir,
        project_id=project_id,
        top_n=3,
    )
    
    if not thumbnails:
        raise HTTPException(500, "Failed to generate thumbnails")
    
    # Convert paths to URLs
    thumbnail_urls = []
    for thumb in thumbnails:
        filename = os.path.basename(thumb["path"])
        thumbnail_urls.append({
            "rank": thumb["rank"],
            "url": f"/outputs/thumbnails/{filename}",
            "timestamp": thumb["timestamp"],
            "visual_quality": thumb["visual_quality"],
            "description": thumb["description"],
            "source_video": thumb["source_video"],
        })
    
    logger.info("Returning %d thumbnails for project %s", len(thumbnail_urls), project_id)
    
    return {
        "thumbnails": thumbnail_urls,
        "count": len(thumbnail_urls),
    }


@router.post("/undo")
async def undo_edit(project_id: str, request: Request):
    """Undo the last edit and restore previous timeline."""
    db = _db(request)
    
    # Get current edit plan
    plan = await db.edit_plans.find_one({"project_id": project_id})
    if not plan:
        raise HTTPException(404, "No edit plan found")
    
    current_version = plan.get("version", 1)
    if current_version <= 1:
        raise HTTPException(400, "Already at first version, cannot undo")
    
    # Check if there's a timeline snapshot for the previous version
    prev_version = current_version - 1
    snapshot = await db.timeline_snapshots.find_one({
        "project_id": project_id,
        "version": prev_version,
    })
    
    if snapshot:
        # Load from snapshot
        prev_timeline = snapshot.get("timeline", {})
        prev_clips = prev_timeline.get("clips", [])
    else:
        # No snapshot, cannot undo (fallback: use history to reconstruct?)
        raise HTTPException(404, f"No snapshot found for version {prev_version}")
    
    if not prev_clips:
        raise HTTPException(400, "Previous timeline is empty")
    
    # Save current timeline as snapshot before undoing (for redo)
    current_snapshot_exists = await db.timeline_snapshots.find_one({
        "project_id": project_id,
        "version": current_version,
    })
    
    if not current_snapshot_exists:
        await db.timeline_snapshots.insert_one({
            "_id": f"{project_id}_v{current_version}",
            "project_id": project_id,
            "version": current_version,
            "timeline": plan.get("timeline", {}),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    
    # Fast concat the proxy preview from previous version
    proxies_dir = os.path.join(settings.upload_dir, project_id, "proxies")
    all_clips_combined = plan.get("timeline", {}).get("clips", []) + plan.get("clip_pool", [])
    proxy_map = await get_existing_proxies(all_clips_combined, proxies_dir)
    
    timeline_clip_ids = [c["clip_id"] for c in sorted(prev_clips, key=lambda x: x.get("order", 0))
                         if c.get("status") == "included"]
    
    proxy_preview_filename = f"{project_id}_proxy.mp4"
    proxy_preview_path = os.path.join(settings.output_dir, proxy_preview_filename)
    
    try:
        await fast_concat_proxies(timeline_clip_ids, proxy_map, proxy_preview_path, project_id)
    except Exception as e:
        logger.warning("Failed to concat proxy on undo: %s", e)
    
    # Update edit plan with previous timeline
    total_effective = sum(c.get("effective_duration", 0) for c in prev_clips)
    
    await db.edit_plans.update_one(
        {"project_id": project_id},
        {
            "$set": {
                "timeline": prev_timeline,
                "version": prev_version,
                "proxy_preview_path": proxy_preview_path,
            },
        },
    )
    
    # Mark conversation messages from undone version as undone
    await db.edit_plans.update_one(
        {"project_id": project_id},
        {"$set": {"conversation.$[elem].undone": True}},
        array_filters=[{"elem.version": current_version}]
    )
    
    logger.info("Undo: Reverted project %s to version %d", project_id, prev_version)
    
    return {
        "success": True,
        "message": "Undone to previous version",
        "version": prev_version,
        "proxy_preview_url": f"/outputs/{proxy_preview_filename}",
        "clips_count": len(prev_clips),
        "total_duration": total_effective,
        "undone_version": current_version,
    }


@router.post("/redo")
async def redo_edit(project_id: str, request: Request):
    """Redo the next edit (if available)."""
    db = _db(request)
    
    # Get current edit plan
    plan = await db.edit_plans.find_one({"project_id": project_id})
    if not plan:
        raise HTTPException(404, "No edit plan found")
    
    current_version = plan.get("version", 1)
    next_version = current_version + 1
    
    # Check if there's a snapshot for the next version
    snapshot = await db.timeline_snapshots.find_one({
        "project_id": project_id,
        "version": next_version,
    })
    
    if not snapshot:
        raise HTTPException(400, "No next version available for redo")
    
    next_timeline = snapshot.get("timeline", {})
    next_clips = next_timeline.get("clips", [])
    
    if not next_clips:
        raise HTTPException(400, "Next timeline is empty")
    
    # Fast concat proxy preview
    proxies_dir = os.path.join(settings.upload_dir, project_id, "proxies")
    all_clips_combined = plan.get("timeline", {}).get("clips", []) + plan.get("clip_pool", [])
    proxy_map = await get_existing_proxies(all_clips_combined, proxies_dir)
    
    timeline_clip_ids = [c["clip_id"] for c in sorted(next_clips, key=lambda x: x.get("order", 0))
                         if c.get("status") == "included"]
    
    proxy_preview_filename = f"{project_id}_proxy.mp4"
    proxy_preview_path = os.path.join(settings.output_dir, proxy_preview_filename)
    
    try:
        await fast_concat_proxies(timeline_clip_ids, proxy_map, proxy_preview_path, project_id)
    except Exception as e:
        logger.warning("Failed to concat proxy on redo: %s", e)
    
    # Update edit plan with next timeline
    total_effective = sum(c.get("effective_duration", 0) for c in next_clips)
    
    await db.edit_plans.update_one(
        {"project_id": project_id},
        {
            "$set": {
                "timeline": next_timeline,
                "version": next_version,
                "proxy_preview_path": proxy_preview_path,
            },
        },
    )
    
    # Un-mark conversation messages from redone version
    await db.edit_plans.update_one(
        {"project_id": project_id},
        {"$set": {"conversation.$[elem].undone": False}},
        array_filters=[{"elem.version": next_version}]
    )
    
    logger.info("Redo: Advanced project %s to version %d", project_id, next_version)
    
    return {
        "success": True,
        "message": "Redone to next version",
        "version": next_version,
        "proxy_preview_url": f"/outputs/{proxy_preview_filename}",
        "clips_count": len(next_clips),
        "total_duration": total_effective,
        "redone_version": next_version,
    }


@router.post("/refine")
async def refine_edit_plan(project_id: str, body: RefineRequest, request: Request):
    """Conversational editing: user provides instruction, Claude refines the edit plan."""
    db = _db(request)
    
    # Get current edit plan
    plan = await db.edit_plans.find_one({"project_id": project_id})
    if not plan:
        raise HTTPException(404, "No edit plan found")
    
    # Get project info for context
    project = await db.projects.find_one({"_id": project_id})
    if not project:
        raise HTTPException(404, "Project not found")

    timeline_clips = plan.get("timeline", {}).get("clips", [])
    clip_pool = plan.get("clip_pool", [])
    target_duration = plan.get("timeline", {}).get("target_duration", 60)
    
    # Build compact timeline text with references
    included_clips = sorted(
        [c for c in timeline_clips if c.get("status") == "included"],
        key=lambda x: x.get("order", 0)
    )
    timeline_text = "\n".join([
        f"[T{i}] {c.get('start_time', 0):.1f}-{c.get('end_time', 0):.1f}s | "
        f"spd:{c.get('speed_factor', 1.0)}x | "
        f"q:{c.get('visual_quality', 5)}/10 | "
        f"src:{c.get('source_video', '?')[:8]} | "
        f"{c.get('description', 'Clip')}"
        for i, c in enumerate(included_clips)
    ])
    
    # Layer 0 pre-boost: Run fast regex search before Claude call
    logger.info("Layer 0 pre-boost: searching for query in instruction")
    pre_boost_matches = await find_clips_by_text(body.instruction, clip_pool)
    pre_boost_clip_ids = {c.get("clip_id") for c in pre_boost_matches[:5]}  # Top 5 matches
    
    # Extract keywords from user instruction for relevance boost
    instruction_lower = body.instruction.lower()
    keywords = [w for w in instruction_lower.split() if len(w) > 2]
    
    # Score each pool clip by keyword relevance
    def keyword_score(clip):
        desc = clip.get("description", "").lower()
        return sum(1 for k in keywords if k in desc)
    
    # Sort: Layer 0 matches first, then keyword matches, then by visual_quality
    def sort_key(clip):
        is_pre_boost = clip.get("clip_id") in pre_boost_clip_ids
        return (-int(is_pre_boost), -keyword_score(clip), -clip.get("visual_quality", 0))
    
    clip_pool_sorted = sorted(clip_pool, key=sort_key)
    
    # Build pool text with [LIKELY MATCH] prefix for pre-boost matches
    pool_lines = []
    for i, c in enumerate(clip_pool_sorted[:50]):
        prefix = "[LIKELY MATCH] " if c.get("clip_id") in pre_boost_clip_ids else ""
        line = (
            f"{prefix}[P{i}] {c.get('start_time', 0):.1f}-{c.get('end_time', 0):.1f}s | "
            f"q:{c.get('visual_quality', 0)}/10 | "
            f"src:{c.get('source_video', '?')[:8]} | "
            f"{c.get('description', 'Action')}"
        )
        pool_lines.append(line)
    
    pool_text = "\n".join(pool_lines)
    
    current_duration = sum(
        c.get("effective_duration", 0) for c in included_clips
    )
    
    # Build conversation context (last 5 turns)
    conversation_history = plan.get("conversation", [])
    active_convo = [m for m in conversation_history if not m.get("undone")]
    # Get last 10 messages (5 user + 5 assistant = 5 turns)
    recent_msgs = active_convo[-10:]
    
    history_text = ""
    if recent_msgs:
        history_lines = []
        for msg in recent_msgs:
            prefix = "User" if msg["role"] == "user" else "Editor"
            history_lines.append(f"  {prefix}: {msg['text']}")
        history_text = f"\nRECENT EDITS:\n" + "\n".join(history_lines) + "\n"
    
    # Get recipe context from project
    recipe_type = project.get("dish_name", "") or project.get("recipe_details", "") or "cooking"
    
    user_prompt = f"""RECIPE: {recipe_type}
TARGET DURATION: {target_duration}s

CURRENT TIMELINE ({len(included_clips)} clips, {current_duration:.0f}s):
{timeline_text}

CLIP POOL (unused, ranked by quality):
{pool_text if pool_text else "(none)"}
{history_text}
USER REQUEST: "{body.instruction}"

Use the apply_edit tool. Reference clips by their T/P index. You may adjust start_time/end_time within a clip's range."""

    # Call Claude with tool_use
    api_key = await _resolve_api_key()
    client = _build_async_client(api_key)
    
    try:
        response = await client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=8192,
            system=REFINE_SYSTEM_PROMPT,
            tools=[REFINE_TOOL],
            tool_choice={"type": "tool", "name": "apply_edit"},
            messages=[{"role": "user", "content": user_prompt}],
        )
        
        # Extract tool use result — no regex needed!
        tool_block = next(
            (b for b in response.content if b.type == "tool_use"), None
        )
        if not tool_block:
            raise HTTPException(400, "Claude did not return a valid edit")
        
        result = tool_block.input
        mode = result.get("mode", "apply")
        changes_summary = result.get("summary", "")
        warnings = result.get("warnings", [])
        
        logger.info("Refine tool response: mode=%s, has_clips=%s, has_candidates=%s, summary=%s",
                    mode, bool(result.get("clips")), bool(result.get("candidates")), changes_summary[:80])
        
        # Smart search fallback: If Claude couldn't find a clip, try smart search
        if should_trigger_smart_search(result, mode):
            logger.info("Smart search triggered: Claude couldn't find clip for: '%s'", body.instruction[:100])
            
            # Send WebSocket progress update
            await ws_manager.send_progress(project_id, {
                "type": "smart_search_progress",
                "layer": 0,
                "message": "Searching for your clip..."
            })
            
            # Combine timeline and pool for comprehensive search
            all_clips = timeline_clips + clip_pool
            
            try:
                search_result = await smart_find_clip(
                    query=body.instruction,
                    all_clips=all_clips,
                    project_id=project_id,
                )
                
                if search_result["type"] == "found":
                    found_clips = search_result.get("clips", [])
                    layer = search_result.get("layer", 0)
                    
                    logger.info("Smart search SUCCESS at Layer %d: found %d clips", layer, len(found_clips))
                    
                    # Send success progress update
                    await ws_manager.send_progress(project_id, {
                        "type": "smart_search_complete",
                        "layer": layer,
                        "found": True,
                        "clips_count": len(found_clips)
                    })
                    
                    # Add found clips to the pool text and re-run Claude
                    extra_pool_lines = []
                    for i, clip in enumerate(found_clips[:5]):  # Top 5 found clips
                        line = (
                            f"[SMART SEARCH MATCH - Layer {layer}] [P{len(clip_pool_sorted) + i}] "
                            f"{clip.get('start_time', 0):.1f}-{clip.get('end_time', 0):.1f}s | "
                            f"q:{clip.get('visual_quality', 5)}/10 | "
                            f"src:{clip.get('source_video', '?')[:8]} | "
                            f"{clip.get('description', 'Found clip')}"
                        )
                        extra_pool_lines.append(line)
                        # Add to clip_pool_sorted for reference resolution
                        clip_pool_sorted.append(clip)
                    
                    # Rebuild prompt with extra clips
                    enhanced_pool_text = pool_text + "\n\n" + "\n".join(extra_pool_lines)
                    
                    enhanced_prompt = f"""RECIPE: {recipe_type}
TARGET DURATION: {target_duration}s

CURRENT TIMELINE ({len(included_clips)} clips, {current_duration:.0f}s):
{timeline_text}

CLIP POOL (unused, ranked by quality):
{enhanced_pool_text}
{history_text}
USER REQUEST: "{body.instruction}"

Use the apply_edit tool. Reference clips by their T/P index. You may adjust start_time/end_time within a clip's range."""
                    
                    # Re-call Claude with enhanced pool
                    logger.info("Re-calling Claude with %d smart-found clips added to pool", len(found_clips))
                    response = await client.messages.create(
                        model="claude-sonnet-4-5",
                        max_tokens=8192,
                        system=REFINE_SYSTEM_PROMPT,
                        tools=[REFINE_TOOL],
                        tool_choice={"type": "tool", "name": "apply_edit"},
                        messages=[{"role": "user", "content": enhanced_prompt}],
                    )
                    
                    # Extract new tool result
                    tool_block = next(
                        (b for b in response.content if b.type == "tool_use"), None
                    )
                    if tool_block:
                        result = tool_block.input
                        mode = result.get("mode", "apply")
                        changes_summary = result.get("summary", "")
                        warnings = result.get("warnings", [])
                        logger.info("Re-run with smart clips: mode=%s, summary=%s", mode, changes_summary[:80])
                    
                elif search_result["type"] == "not_found":
                    # Layer 5: Honest admission
                    logger.info("Smart search exhausted all layers: not found")
                    
                    # Send not found progress update
                    await ws_manager.send_progress(project_id, {
                        "type": "smart_search_complete",
                        "found": False
                    })
                    
                    # Return Layer 5 honest admission to frontend
                    not_found_summary = search_result.get("summary", "Couldn't find that clip.")
                    suggestions = search_result.get("suggestions", [])
                    
                    new_version = plan.get("version", 1)
                    user_msg = {
                        "id": str(uuid4()),
                        "role": "user",
                        "text": body.instruction,
                        "version": new_version,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "undone": False
                    }
                    assistant_msg = {
                        "id": str(uuid4()),
                        "role": "assistant",
                        "text": not_found_summary,
                        "version": new_version,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "undone": False,
                        "is_not_found": True,
                        "suggestions": suggestions,
                    }
                    
                    await db.edit_plans.update_one(
                        {"project_id": project_id},
                        {"$push": {"conversation": {"$each": [user_msg, assistant_msg]}}},
                    )
                    
                    return {
                        "type": "not_found",
                        "summary": not_found_summary,
                        "suggestions": suggestions,
                        "conversation_messages": [user_msg, assistant_msg],
                    }
            
            except Exception as e:
                logger.warning("Smart search failed: %s", e, exc_info=True)
                # Continue with original Claude result if smart search fails
                await ws_manager.send_progress(project_id, {
                    "type": "smart_search_error",
                    "message": "Search failed, using original results"
                })
        
        # Branch on mode: propose vs apply
        if mode == "propose":
            # Don't render anything - just return the proposal
            candidates = result.get("candidates", [])
            
            # Enrich candidates with thumbnail info
            enriched_candidates = []
            for cand in candidates:
                clip_ref = cand.get("clip_ref", "")
                source_clip = resolve_single_clip_ref(clip_ref, included_clips, clip_pool_sorted)
                if source_clip:
                    cand["start_time"] = source_clip.get("start_time", 0)
                    cand["end_time"] = source_clip.get("end_time", 0)
                    cand["visual_quality"] = source_clip.get("visual_quality", 5)
                    cand["source_video"] = source_clip.get("source_video", "")
                    cand["clip_id"] = source_clip.get("clip_id", "")
                    cand["action_id"] = source_clip.get("clip_id", "")  # Use clip_id for thumbnail lookup
                    cand["thumbnail_path"] = source_clip.get("thumbnail_path", "")
                enriched_candidates.append(cand)
            
            # Create conversation messages (user + AI proposal)
            new_version = plan.get("version", 1)  # Don't bump for proposals
            
            user_msg = {
                "id": str(uuid4()),
                "role": "user",
                "text": body.instruction,
                "version": new_version,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "undone": False
            }
            assistant_msg = {
                "id": str(uuid4()),
                "role": "assistant",
                "text": changes_summary,
                "version": new_version,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "undone": False,
                "is_proposal": True,
                "candidates": enriched_candidates,
                "proposed_action": result.get("proposed_action", ""),
            }
            
            # Save conversation (no timeline change)
            await db.edit_plans.update_one(
                {"project_id": project_id},
                {"$push": {"conversation": {"$each": [user_msg, assistant_msg]}}},
            )
            
            logger.info("Refine proposal: %d candidates, summary: %s", 
                       len(enriched_candidates), changes_summary[:100])
            
            return {
                "type": "proposal",
                "summary": changes_summary,
                "candidates": enriched_candidates,
                "proposed_action": result.get("proposed_action", ""),
                "warnings": warnings,
                "conversation_messages": [user_msg, assistant_msg],
            }
        
        # mode == "apply" - execute edit
        raw_clips = result.get("clips", [])
        
        # CRITICAL FIX: If AI returned apply mode with empty clips but described changes,
        # re-call with explicit instruction to include the clips array
        if not raw_clips and not result.get("candidates"):
            confirm_keywords = ["ready", "confirmed", "keeping", "no change", "looks good", "proceed", "finalized"]
            is_confirmation = any(kw in changes_summary.lower() for kw in confirm_keywords)
            
            if not is_confirmation:
                # AI described changes but forgot to include clips - retry once
                logger.warning("AI returned apply with empty clips but described changes, retrying with nudge")
                retry_prompt = user_prompt + f"\n\nIMPORTANT: You previously responded with summary='{changes_summary}' but EMPTY clips array. You MUST include the COMPLETE new timeline in the clips array. Return ALL clips (T-refs for unchanged, modified as needed). Do NOT return empty clips."
                try:
                    retry_response = await client.messages.create(
                        model="claude-sonnet-4-5",
                        max_tokens=4096,
                        system=REFINE_SYSTEM_PROMPT,
                        tools=[REFINE_TOOL],
                        tool_choice={"type": "tool", "name": "apply_edit"},
                        messages=[{"role": "user", "content": retry_prompt}],
                    )
                    retry_block = next((b for b in retry_response.content if b.type == "tool_use"), None)
                    if retry_block:
                        retry_result = retry_block.input
                        retry_clips = retry_result.get("clips", [])
                        if retry_clips:
                            logger.info("Retry succeeded: got %d clips", len(retry_clips))
                            raw_clips = retry_clips
                            result = retry_result
                            changes_summary = retry_result.get("summary", changes_summary)
                        else:
                            logger.warning("Retry also returned empty clips")
                except Exception as retry_e:
                    logger.warning("Retry failed: %s", retry_e)
        
        if not raw_clips:
            # If Claude returned no clips but has candidates, treat as propose
            if result.get("candidates"):
                logger.warning("Claude returned mode=apply but no clips with candidates present, treating as propose")
                mode = "propose"
                # Re-run the propose branch by falling through
                candidates = result.get("candidates", [])
                enriched_candidates = []
                for cand in candidates:
                    clip_ref = cand.get("clip_ref", "")
                    source_clip = resolve_single_clip_ref(clip_ref, included_clips, clip_pool_sorted)
                    if source_clip:
                        cand["start_time"] = source_clip.get("start_time", 0)
                        cand["end_time"] = source_clip.get("end_time", 0)
                        cand["visual_quality"] = source_clip.get("visual_quality", 5)
                        cand["source_video"] = source_clip.get("source_video", "")
                        cand["action_id"] = source_clip.get("action_id", "")
                    enriched_candidates.append(cand)
                
                new_version = plan.get("version", 1)
                user_msg = {
                    "id": str(uuid4()),
                    "role": "user",
                    "text": body.instruction,
                    "version": new_version,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "undone": False
                }
                assistant_msg = {
                    "id": str(uuid4()),
                    "role": "assistant",
                    "text": changes_summary,
                    "version": new_version,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "undone": False,
                    "is_proposal": True
                }
                await db.edit_plans.update_one(
                    {"project_id": project_id},
                    {"$push": {"conversation": {"$each": [user_msg, assistant_msg]}}},
                )
                return {
                    "type": "proposal",
                    "summary": changes_summary,
                    "candidates": enriched_candidates,
                    "proposed_action": result.get("proposed_action", ""),
                    "warnings": warnings,
                    "conversation_messages": [user_msg, assistant_msg],
                }
            
            # If truly no clips and no candidates, check if this is a "keep current" confirmation
            logger.warning("Claude returned empty timeline with no candidates, summary: %s", changes_summary[:100])
            
            # If summary suggests confirmation/no-change, just acknowledge without error
            confirm_keywords = ["ready", "confirmed", "keeping", "no change", "looks good", "proceed"]
            is_confirmation = any(kw in changes_summary.lower() for kw in confirm_keywords)
            new_version = plan.get("version", 1)
            user_msg = {
                "id": str(uuid4()),
                "role": "user",
                "text": body.instruction,
                "version": new_version,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "undone": False
            }
            assistant_msg = {
                "id": str(uuid4()),
                "role": "assistant",
                "text": changes_summary or "I couldn't process that edit. Could you try rephrasing?",
                "version": new_version,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "undone": False
            }
            await db.edit_plans.update_one(
                {"project_id": project_id},
                {"$push": {"conversation": {"$each": [user_msg, assistant_msg]}}},
            )
            return {
                "type": "proposal",
                "summary": changes_summary or "I couldn't process that edit. Could you try rephrasing?",
                "candidates": [],
                "proposed_action": "",
                "warnings": warnings or ["Could not generate a valid edit from this instruction"],
                "conversation_messages": [user_msg, assistant_msg],
            }
        
        logger.info("Refine via tool_use: %d clips, summary: %s", len(raw_clips), changes_summary[:100])
        if warnings:
            logger.info("Refine warnings: %s", warnings)
        
        # Resolve clip references (T0, P0, etc.) to actual clip data
        new_clips = []
        for i, rc in enumerate(raw_clips):
            clip_ref = rc.get("clip_ref", "")
            source_clip = None
            
            if clip_ref.startswith("T") and clip_ref[1:].isdigit():
                idx = int(clip_ref[1:])
                if idx < len(included_clips):
                    source_clip = included_clips[idx]
            elif clip_ref.startswith("P") and clip_ref[1:].isdigit():
                idx = int(clip_ref[1:])
                if idx < len(clip_pool_sorted):
                    source_clip = clip_pool_sorted[idx]
            
            # Fallback: match by timestamp + source hint
            if not source_clip:
                all_known = timeline_clips + clip_pool
                source_hint = rc.get("source_hint", "")
                best_match = None
                best_diff = float("inf")
                for kc in all_known:
                    diff = abs(kc.get("start_time", 0) - rc.get("start_time", 0))
                    end_diff = abs(kc.get("end_time", 0) - rc.get("end_time", 0))
                    if diff < 1.0 and end_diff < 2.0:
                        # Prefer source_hint match
                        src_match = source_hint and kc.get("source_video", "").startswith(source_hint)
                        effective_diff = diff * (0.1 if src_match else 1.0)
                        if effective_diff < best_diff:
                            best_match = kc
                            best_diff = effective_diff
                if best_match:
                    source_clip = best_match
            
            clip = {
                "order": i,
                "status": "included",
                "added_by": "user_refine",
                "start_time": rc.get("start_time", 0),
                "end_time": rc.get("end_time", 0),
                "speed_factor": rc.get("speed_factor", 1.0),
                "description": rc.get("description", "Clip"),
            }
            
            duration = clip["end_time"] - clip["start_time"]
            clip["duration"] = duration
            clip["effective_duration"] = duration / clip["speed_factor"]
            
            if source_clip:
                clip["clip_id"] = source_clip.get("clip_id")
                clip["source_video"] = source_clip.get("source_video", "")
                clip["source_path"] = source_clip.get("source_path", "")
                clip["thumbnail_path"] = source_clip.get("thumbnail_path")
                clip["action_id"] = source_clip.get("action_id")
                clip["recipe_step"] = source_clip.get("recipe_step")
                clip["proxy_path"] = source_clip.get("proxy_path")
            
            # Fallback source_path from video_path_map
            video_path_map = plan.get("video_path_map", {})
            if not clip.get("source_path") or not os.path.exists(clip.get("source_path", "")):
                source_video = clip.get("source_video", "")
                clip["source_path"] = video_path_map.get(source_video, "")
            
            if not clip.get("clip_id"):
                clip["clip_id"] = str(uuid4())
            
            new_clips.append(clip)
        
        total_effective = sum(c["effective_duration"] for c in new_clips)
        
        # Bump version
        new_version = plan.get("version", 1) + 1
        history_entry = {
            "version": new_version,
            "source": "user_refine",
            "action": f"conversational_edit",
            "instruction": body.instruction,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        # Save current timeline as snapshot (for undo/redo)
        current_version = plan.get("version", 1)
        current_snapshot_exists = await db.timeline_snapshots.find_one({
            "project_id": project_id,
            "version": current_version,
        })
        
        if not current_snapshot_exists:
            await db.timeline_snapshots.insert_one({
                "_id": f"{project_id}_v{current_version}",
                "project_id": project_id,
                "version": current_version,
                "timeline": plan.get("timeline", {}),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        
        # Update edit plan in DB
        await db.edit_plans.update_one(
            {"project_id": project_id},
            {
                "$set": {
                    "timeline.clips": new_clips,
                    "timeline.total_effective_duration": total_effective,
                    "version": new_version,
                    "status": "draft",
                },
                "$push": {"history": history_entry},
            },
        )
        
        # Update edit_decisions for backward compat
        await db.edit_decisions.delete_many({"project_id": project_id})
        for clip in new_clips:
            doc = {
                "project_id": project_id,
                "sequence_order": clip["order"],
                "action_id": clip.get("action_id"),
                "source_path": clip.get("source_path", ""),
                "start_time": clip["start_time"],
                "end_time": clip["end_time"],
                "duration": clip["duration"],
                "speed_factor": clip.get("speed_factor", 1.0),
                "description": clip.get("description", ""),
                "reason": clip.get("reason", body.instruction),
                "filename": clip.get("source_video", ""),
            }
            await db.edit_decisions.insert_one(doc)
        
        logger.info("Edit plan refined: %d clips, %.1fs duration (instruction: %s)",
                    len(new_clips), total_effective, body.instruction[:50])
        
        # ---- PROXY SYSTEM: Fast preview with proxy clips ---- #
        # 1. Check which clips already have proxies
        proxies_dir = os.path.join(settings.upload_dir, project_id, "proxies")
        
        # Get existing proxies from all clips (timeline + pool)
        all_clips_combined = timeline_clips + clip_pool
        existing_proxy_map = await get_existing_proxies(all_clips_combined, proxies_dir)
        
        # 2. Identify new clips that need proxy rendering
        new_clips_to_render = identify_new_clips(new_clips, existing_proxy_map)
        
        # 3. Pre-render only NEW clips (most clips already have proxies!)
        if new_clips_to_render:
            logger.info("Pre-rendering %d new proxy clips", len(new_clips_to_render))
            # Get aspect ratio from project
            aspect_ratio = project.get("aspect_ratio", "16:9")
            new_proxy_map = await pre_render_proxy_clips(
                project_id,
                new_clips_to_render,
                proxies_dir,
                db,
                aspect_ratio=aspect_ratio,
            )
            # Merge with existing proxies
            existing_proxy_map.update(new_proxy_map)
        
        # 4. Fast concat proxy clips (2-3 seconds!)
        timeline_clip_ids = [c["clip_id"] for c in sorted(new_clips, key=lambda x: x["order"])]
        proxy_preview_filename = f"{project_id}_proxy.mp4"
        proxy_preview_path = os.path.join(settings.output_dir, proxy_preview_filename)
        
        try:
            await fast_concat_proxies(timeline_clip_ids, existing_proxy_map, proxy_preview_path, project_id)
            
            # Save proxy preview path in edit plan
            await db.edit_plans.update_one(
                {"project_id": project_id},
                {"$set": {"proxy_preview_path": proxy_preview_path}},
            )
            logger.info("Proxy preview updated instantly: %s", proxy_preview_path)
            
        except Exception as e:
            logger.warning("Failed to create proxy preview: %s", e)
        
        # Create conversation messages
        user_msg = {
            "id": str(uuid4()),
            "role": "user",
            "text": body.instruction,
            "version": new_version,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "undone": False
        }
        assistant_msg = {
            "id": str(uuid4()),
            "role": "assistant",
            "text": changes_summary,
            "version": new_version,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "undone": False
        }
        
        # Push conversation messages to edit plan
        await db.edit_plans.update_one(
            {"project_id": project_id},
            {"$push": {"conversation": {"$each": [user_msg, assistant_msg]}}},
        )
        
        # 5. Queue HD render in background (non-blocking)
        asyncio.create_task(render_from_edit_plan(db, project_id))
        
        return {
            "status": "editing",
            "proxy_preview_url": f"/outputs/{proxy_preview_filename}",
            "hd_rendering": True,
            "changes_summary": changes_summary,
            "version": new_version,
            "clips_count": len(new_clips),
            "total_duration": total_effective,
            "conversation_messages": [user_msg, assistant_msg],
        }
        
    except Exception as e:
        logger.exception("Failed to refine edit plan")
        raise HTTPException(500, f"Refine failed: {str(e)}")


@router.post("/smart-search")
async def smart_search_clip(project_id: str, body: SmartSearchRequest, request: Request):
    """Explicitly trigger smart clip finding for manual search."""
    db = _db(request)
    
    # Get current edit plan
    plan = await db.edit_plans.find_one({"project_id": project_id})
    if not plan:
        raise HTTPException(404, "No edit plan found")
    
    timeline_clips = plan.get("timeline", {}).get("clips", [])
    clip_pool = plan.get("clip_pool", [])
    
    # Combine all clips for comprehensive search
    all_clips = timeline_clips + clip_pool
    
    logger.info("Smart search triggered manually for project %s, query: '%s'", project_id, body.query)
    
    # Send initial progress update
    await ws_manager.send_progress(project_id, {
        "type": "smart_search_progress",
        "layer": 0,
        "message": "Starting smart search..."
    })
    
    try:
        search_result = await smart_find_clip(
            query=body.query,
            all_clips=all_clips,
            project_id=project_id,
        )
        
        if search_result["type"] == "found":
            found_clips = search_result.get("clips", [])
            layer = search_result.get("layer", 0)
            
            logger.info("Smart search found %d clips at Layer %d", len(found_clips), layer)
            
            # Send success progress update
            await ws_manager.send_progress(project_id, {
                "type": "smart_search_complete",
                "layer": layer,
                "found": True,
                "clips_count": len(found_clips)
            })
            
            # Enrich clips with thumbnail info
            enriched_clips = []
            for clip in found_clips:
                clip_copy = clip.copy()
                # Add thumbnail path if available
                clip_copy["action_id"] = clip.get("clip_id", "")
                enriched_clips.append(clip_copy)
            
            # Optionally add discovered clips to the project's clip pool
            # (for Layer 3 which creates new clips from gaps)
            new_clips = [c for c in found_clips if c.get("discovered")]
            if new_clips:
                logger.info("Adding %d newly discovered clips to clip pool", len(new_clips))
                # Append to clip_pool in database
                await db.edit_plans.update_one(
                    {"project_id": project_id},
                    {"$push": {"clip_pool": {"$each": new_clips}}},
                )
            
            return {
                "type": "found",
                "layer": layer,
                "clips": enriched_clips,
                "clips_count": len(enriched_clips),
                "message": f"Found {len(enriched_clips)} matching clip(s) at Layer {layer}",
            }
        
        else:
            # Not found
            logger.info("Smart search exhausted all layers: not found")
            
            # Send not found progress update
            await ws_manager.send_progress(project_id, {
                "type": "smart_search_complete",
                "found": False
            })
            
            return {
                "type": "not_found",
                "summary": search_result.get("summary", "Couldn't find that clip."),
                "suggestions": search_result.get("suggestions", []),
            }
    
    except Exception as e:
        logger.exception("Smart search failed")
        
        # Send error progress update
        await ws_manager.send_progress(project_id, {
            "type": "smart_search_error",
            "message": str(e)
        })
        
        raise HTTPException(500, f"Smart search failed: {str(e)}")
