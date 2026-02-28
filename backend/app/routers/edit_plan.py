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
- "boring part" = low-action footage"""

REFINE_TOOL = {
    "name": "apply_edit",
    "description": "Apply the video edit changes and provide a cooking-aware summary",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "1-3 sentence cooking-aware summary of what changed. Reference food/cooking terms, not timecodes. Mention new total duration."
            },
            "clips": {
                "type": "array",
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
                            "description": "First 8 chars of source video filename, from src: field"
                        }
                    },
                    "required": ["clip_ref", "start_time", "end_time", "speed_factor", "description"]
                }
            },
            "warnings": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional warnings about issues or impossible requests"
            }
        },
        "required": ["summary", "clips"]
    }
}

router = APIRouter(prefix="/api/projects/{project_id}/edit-plan", tags=["edit-plan"])


def _db(request: Request):
    return request.app.state.db


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
    
    pool_text = "\n".join([
        f"[P{i}] {c.get('start_time', 0):.1f}-{c.get('end_time', 0):.1f}s | "
        f"q:{c.get('visual_quality', 0)}/10 | "
        f"src:{c.get('source_video', '?')[:8]} | "
        f"{c.get('description', 'Action')}"
        for i, c in enumerate(clip_pool[:20])
    ])
    
    current_duration = sum(
        c.get("effective_duration", 0) for c in included_clips
    )
    
    # Build conversation context (last 3 turns)
    conversation_history = plan.get("conversation", [])
    active_convo = [m for m in conversation_history if not m.get("undone")]
    # Get last 6 messages (3 user + 3 assistant = 3 turns)
    recent_msgs = active_convo[-6:]
    
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
            max_tokens=2048,
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
        changes_summary = result.get("summary", f"Updated to {len(result.get('clips', []))} clips")
        warnings = result.get("warnings", [])
        raw_clips = result.get("clips", [])
        
        if not raw_clips:
            raise HTTPException(400, "Claude returned empty timeline")
        
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
                if idx < len(clip_pool):
                    source_clip = clip_pool[idx]
            
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
            new_proxy_map = await pre_render_proxy_clips(
                project_id,
                new_clips_to_render,
                proxies_dir,
                db,
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
