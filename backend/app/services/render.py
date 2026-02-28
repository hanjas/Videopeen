"""Render pipeline — runs after user confirms edit plan."""

from __future__ import annotations

import asyncio
import logging
import os

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import settings
from app.models.project import ProjectStatus
from app.services.video_stitcher import stitch_clips_v2
from app.services.text_overlay import apply_text_overlays
from app.websocket import ws_manager

logger = logging.getLogger(__name__)


async def _update_project(db, project_id, status, progress, step, **extra):
    update = {"status": status.value, "progress": round(progress, 1), "current_step": step, **extra}
    await db.projects.update_one({"_id": project_id}, {"$set": update})
    await ws_manager.send_progress(project_id, {
        "status": status.value, "progress": round(progress, 1), "step": step,
    })


async def render_from_edit_plan(db: AsyncIOMotorDatabase, project_id: str) -> None:
    """Stitch final video from the confirmed edit plan."""
    project = await db.projects.find_one({"_id": project_id})
    if not project:
        logger.error("Project %s not found", project_id)
        return

    try:
        # Get the edit plan
        edit_plan = await db.edit_plans.find_one({"project_id": project_id})
        if not edit_plan:
            raise ValueError("No edit plan found for this project")

        clips = edit_plan.get("timeline", {}).get("clips", [])
        if not clips:
            raise ValueError("Edit plan has no clips")

        await _update_project(db, project_id, ProjectStatus.STITCHING, 85,
                              f"Stitching {len(clips)} clips...")

        # Build stitch entries from edit plan
        stitch_entries = []
        for clip in sorted(clips, key=lambda c: c.get("order", 0)):
            if clip.get("status") != "included":
                continue
            stitch_entries.append({
                "source_path": clip["source_path"],
                "start_time": clip["start_time"],
                "end_time": clip["end_time"],
                "speed_factor": clip.get("speed_factor", 1.0),
            })

        if not stitch_entries:
            raise ValueError("No included clips to stitch")

        # Get aspect ratio and transition settings from project
        aspect_ratio = project.get("aspect_ratio", "16:9")
        transition_type = project.get("transition_type", "fade")
        transition_duration = project.get("transition_duration", 0.5)
        
        # Check if there are text overlays to apply
        text_overlays = edit_plan.get("text_overlays", [])
        
        if text_overlays:
            # Render to temp file first, then apply overlays
            temp_filename = f"{project_id}_no_overlays.mp4"
            temp_path = os.path.join(settings.output_dir, temp_filename)
            
            await asyncio.to_thread(
                stitch_clips_v2, 
                stitch_entries, 
                temp_path, 
                aspect_ratio,
                transition_type,
                transition_duration,
            )
            
            await _update_project(db, project_id, ProjectStatus.STITCHING, 92,
                                  f"Applying {len(text_overlays)} text overlays...")
            
            # Apply text overlays (final output)
            output_filename = f"{project_id}_final.mp4"
            output_path = os.path.join(settings.output_dir, output_filename)
            
            await asyncio.to_thread(
                apply_text_overlays,
                temp_path,
                output_path,
                text_overlays,
                aspect_ratio,
            )
            
            # Clean up temp file
            try:
                os.remove(temp_path)
                logger.info("Cleaned up temp file: %s", temp_path)
            except Exception as e:
                logger.warning("Failed to remove temp file %s: %s", temp_path, e)
        else:
            # No overlays, render directly to final output
            output_filename = f"{project_id}_final.mp4"
            output_path = os.path.join(settings.output_dir, output_filename)
            
            await asyncio.to_thread(
                stitch_clips_v2, 
                stitch_entries, 
                output_path, 
                aspect_ratio,
                transition_type,
                transition_duration,
            )

        # Update edit plan status
        await db.edit_plans.update_one(
            {"project_id": project_id},
            {"$set": {"status": "completed"}},
        )

        await _update_project(
            db, project_id, ProjectStatus.COMPLETED, 100, "Done!",
            output_path=output_path,
        )
        logger.info("Render completed for project %s → %s", project_id, output_path)

    except Exception as exc:
        logger.exception("Render failed for project %s", project_id)
        await db.edit_plans.update_one(
            {"project_id": project_id},
            {"$set": {"status": "failed"}},
        )
        await _update_project(
            db, project_id, ProjectStatus.ERROR, 0,
            f"Render error: {str(exc)[:200]}",
        )
