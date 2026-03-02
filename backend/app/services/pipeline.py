"""Orchestrate the V3 action-based video processing pipeline.

New pipeline:
  1. Dense frame extraction (1 frame every 2s from each video)
  2. Phase 1: Action timeline detection (Claude sees temporal flow)
  3. Phase 2: AI edit decision (Claude acts as editor)
  4. Stitch final output with speed ramps
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import settings
from app.models.project import ProjectStatus
from app.services.video_processor import extract_dense_frames, DenseFrameResult
from app.services.video_analyzer import detect_actions_for_video, create_edit_plan
from app.services.video_stitcher import stitch_clips_v2
from app.services.proxy_renderer import pre_render_proxy_clips, fast_concat_proxies
from app.services.thumbnail import get_best_thumbnail_path
from app.websocket import ws_manager

logger = logging.getLogger(__name__)


async def _update_project(
    db: AsyncIOMotorDatabase,
    project_id: str,
    status: ProjectStatus,
    progress: float,
    current_step: str,
    **extra: Any,
) -> None:
    """Update project status in MongoDB and broadcast via WebSocket."""
    update: dict[str, Any] = {
        "status": status.value,
        "progress": round(progress, 1),
        "current_step": current_step,
        **extra,
    }
    await db.projects.update_one({"_id": project_id}, {"$set": update})
    await ws_manager.send_progress(project_id, {
        "status": status.value,
        "progress": round(progress, 1),
        "step": current_step,
    })


def _build_recipe_context(project: dict) -> dict:
    """Build recipe context from project data."""
    dish_name = project.get("dish_name", "")
    recipe_details = project.get("recipe_details", "")

    steps = []
    if recipe_details:
        step_pattern = r'(?:^|\n)\s*(?:step\s*)?\d+[\.\):\-]\s*(.+?)(?=\n\s*(?:step\s*)?\d+[\.\):\-]|\Z)'
        matches = re.findall(step_pattern, recipe_details, re.IGNORECASE | re.DOTALL)
        if matches:
            steps = [m.strip() for m in matches if m.strip()]

        if not steps:
            lines = [l.strip() for l in recipe_details.split('\n') if l.strip() and len(l.strip()) > 10]
            if len(lines) >= 2:
                steps = lines

        if not steps:
            sentences = re.split(r'(?<=[.!])\s+', recipe_details)
            steps = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 15]

    return {
        "dish_name": dish_name,
        "recipe_steps": steps,
    }


async def run_pipeline(db: AsyncIOMotorDatabase, project_id: str) -> None:
    """Execute the V3 action-based pipeline."""
    project = await db.projects.find_one({"_id": project_id})
    if not project:
        logger.error("Project %s not found", project_id)
        return

    try:
        # ------------------------------------------------------------------ #
        # Step 1: Dense frame extraction
        # ------------------------------------------------------------------ #
        await _update_project(db, project_id, ProjectStatus.PROCESSING, 5,
                              "Extracting frames from videos...")

        clips = await db.video_clips.find({"project_id": project_id}).to_list(None)
        if not clips:
            raise ValueError("No video clips uploaded for this project")

        all_frame_results: list[DenseFrameResult] = []
        video_path_map: dict[str, str] = {}  # filename -> full path

        for ci, clip in enumerate(clips):
            video_path = clip["original_path"]
            if not os.path.exists(video_path):
                logger.warning("Video file missing: %s", video_path)
                continue

            frame_dir = os.path.join(settings.upload_dir, project_id, "frames")

            result = await asyncio.to_thread(
                extract_dense_frames,
                video_path, frame_dir,
                frame_interval=0.5,  # 2fps for SSIM scene selection
                video_index=ci,
            )
            all_frame_results.append(result)
            
            video_name = os.path.basename(video_path)
            video_path_map[video_name] = video_path

            await db.video_clips.update_one(
                {"_id": clip["_id"]},
                {"$set": {"duration": result.total_duration}},
            )

            progress = 5 + (15 * (ci + 1) / len(clips))
            await _update_project(db, project_id, ProjectStatus.PROCESSING, progress,
                                  f"Extracting frames: {ci+1}/{len(clips)} videos done "
                                  f"({sum(len(r.frame_paths) for r in all_frame_results)} frames)")

        total_frames = sum(len(r.frame_paths) for r in all_frame_results)
        total_duration = sum(r.total_duration for r in all_frame_results)
        logger.info("Total: %d frames from %d videos (%.1fs footage)",
                     total_frames, len(all_frame_results), total_duration)

        # ------------------------------------------------------------------ #
        # Step 2: Phase 1 — Action Timeline Detection
        # ------------------------------------------------------------------ #
        await _update_project(db, project_id, ProjectStatus.ANALYZING, 25,
                              f"Detecting actions in {total_frames} frames...")

        recipe_context = _build_recipe_context(project)
        logger.info("Recipe: %s, %d steps", recipe_context["dish_name"],
                     len(recipe_context["recipe_steps"]))

        all_actions: list[dict] = []
        video_sources: list[dict] = []

        # Calculate total batches across all videos for accurate progress
        total_batches = sum(
            max(1, (len(fr.frame_paths) + 14) // 15) for fr in all_frame_results
        )
        batches_done = 0

        for ci, frame_result in enumerate(all_frame_results):
            video_name = os.path.basename(frame_result.video_path)

            async def _on_batch(batch_num: int, n_batches: int, n_actions: int,
                                _ci=ci, _total=total_batches) -> None:
                nonlocal batches_done
                batches_done = sum(
                    max(1, (len(all_frame_results[j].frame_paths) + 14) // 15)
                    for j in range(_ci)
                ) + batch_num
                progress = 25 + (35 * batches_done / _total)
                await _update_project(
                    db, project_id, ProjectStatus.ANALYZING, progress,
                    f"Detecting actions: batch {batches_done}/{_total} "
                    f"({n_actions + len(all_actions)} actions found)")

            actions = await detect_actions_for_video(
                frame_paths=frame_result.frame_paths,
                frame_timestamps=frame_result.frame_timestamps,
                recipe_context=recipe_context,
                video_name=video_name,
                batch_size=15,
                on_batch_done=_on_batch,
            )
            
            # Offset action IDs to be globally unique
            offset = len(all_actions)
            for a in actions:
                a["action_id"] = a["action_id"] + offset
                a["video_index"] = ci
            
            all_actions.extend(actions)
            video_sources.append({
                "name": video_name,
                "path": frame_result.video_path,
                "duration": frame_result.total_duration,
                "n_actions": len(actions),
            })

            progress = 25 + (35 * (ci + 1) / len(all_frame_results))
            await _update_project(db, project_id, ProjectStatus.ANALYZING, progress,
                                  f"Detected {len(all_actions)} actions across {ci+1}/{len(all_frame_results)} videos")

        logger.info("Total actions detected: %d across %d videos",
                     len(all_actions), len(video_sources))

        # ------------------------------------------------------------------ #
        # Reconciliation: Compare detected actions against recipe
        # ------------------------------------------------------------------ #
        reconciliation = {}
        try:
            from app.services.reconciliation import reconcile_actions_with_recipe
            
            reconciliation = await reconcile_actions_with_recipe(
                all_actions, recipe_context, all_frame_results, video_path_map
            )
            
            # Log findings
            if reconciliation.get("missing_ingredients"):
                missing_list = [m["ingredient"] for m in reconciliation["missing_ingredients"]]
                logger.warning("Reconciliation: %d recipe ingredients not detected: %s",
                               len(missing_list), missing_list)
            
            if reconciliation.get("suspicious_gaps"):
                logger.info("Reconciliation: %d suspicious gaps found",
                           len(reconciliation["suspicious_gaps"]))
            
            logger.info("Reconciliation: %d/%d ingredients matched (%.1f%% coverage)",
                       len(reconciliation.get("matched_ingredients", [])),
                       reconciliation.get("total_ingredients", 0),
                       reconciliation.get("match_rate", 0))
        except Exception as e:
            logger.warning("Reconciliation failed (non-blocking): %s", e)
            reconciliation = {"status": "error", "error": str(e)}

        # Save actions to DB
        for action in all_actions:
            doc = {
                "_id": str(uuid.uuid4()),
                "project_id": project_id,
                "action_id": action["action_id"],
                "source_video": action.get("source_video", ""),
                "start_time": action.get("start_time", 0),
                "end_time": action.get("end_time", 0),
                "description": action.get("description", ""),
                "recipe_step": action.get("recipe_step"),
                "action_type": action.get("action_type", ""),
                "visual_quality": action.get("visual_quality", 0),
                "shows_action_moment": action.get("shows_action_moment", False),
            }
            await db.video_analyses.insert_one(doc)

        # ------------------------------------------------------------------ #
        # Step 3: Phase 2 — AI Edit Decision
        # ------------------------------------------------------------------ #
        await _update_project(db, project_id, ProjectStatus.SELECTING, 65,
                              "Claude creating edit plan...")

        # Collect best keyframes for visual reference
        best_keyframes: list[tuple[int, str]] = []
        for action in all_actions:
            key_ts = action.get("key_frame_timestamp")
            if key_ts is not None:
                # Find closest frame
                video_name = action.get("source_video", "")
                for fr in all_frame_results:
                    if os.path.basename(fr.video_path) == video_name:
                        # Find closest timestamp
                        closest_idx = min(
                            range(len(fr.frame_timestamps)),
                            key=lambda i: abs(fr.frame_timestamps[i] - key_ts),
                        )
                        best_keyframes.append((action["action_id"], fr.frame_paths[closest_idx]))
                        break

        # Limit to 15 best keyframes (highest visual quality actions)
        if len(best_keyframes) > 15:
            quality_map = {a["action_id"]: a.get("visual_quality", 0) for a in all_actions}
            best_keyframes.sort(key=lambda x: quality_map.get(x[0], 0), reverse=True)
            best_keyframes = best_keyframes[:15]

        target_duration = project.get("output_duration", 60)

        edit_result = await create_edit_plan(
            recipe_context, all_actions, target_duration,
            video_sources, best_keyframes,
        )

        edit_plan = edit_result.get("edit_plan", [])
        logger.info("Edit plan: %d clips, coverage: %s%%, missing: %s",
                     len(edit_plan),
                     edit_result.get("coverage_pct", "?"),
                     edit_result.get("missing_steps", []))

        if not edit_plan:
            raise ValueError("Claude returned empty edit plan")

        # ------------------------------------------------------------------ #
        # Step 4: Build edit plan entries, generate thumbnails, save to DB
        # ------------------------------------------------------------------ #
        await _update_project(db, project_id, ProjectStatus.SELECTING, 80,
                              f"Preparing {len(edit_plan)} clips...")

        # Build resolved clips with source paths
        resolved_clips = []
        for i, clip in enumerate(edit_plan):
            source_name = clip.get("source_video", "")
            source_path = video_path_map.get(source_name, "")
            
            if not source_path:
                for name, path in video_path_map.items():
                    if source_name in name or name in source_name:
                        source_path = path
                        break
            
            if not source_path:
                logger.warning("Cannot resolve source video: %s", source_name)
                continue

            start = clip.get("start_time", 0)
            end = clip.get("end_time", 0)
            speed = clip.get("speed_factor", 1.0)
            duration = end - start

            if duration <= 0:
                logger.warning("Invalid clip duration: %s", clip)
                continue

            # Generate thumbnail from closest extracted frame
            thumbnail_path = None
            thumb_ts = start + (duration * 0.33)  # 33% mark
            for fr in all_frame_results:
                if os.path.basename(fr.video_path) == source_name:
                    closest_idx = min(
                        range(len(fr.frame_timestamps)),
                        key=lambda idx: abs(fr.frame_timestamps[idx] - thumb_ts),
                    )
                    thumbnail_path = fr.frame_paths[closest_idx]
                    break

            resolved_clips.append({
                "clip_id": str(uuid.uuid4()),
                "order": i,
                "source_video": source_name,
                "source_path": source_path,
                "start_time": start,
                "end_time": end,
                "duration": duration,
                "speed_factor": speed,
                "effective_duration": duration / speed,
                "action_id": clip.get("action_id"),
                "description": clip.get("description", ""),
                "reason": clip.get("reason", ""),
                "recipe_step": clip.get("recipe_step"),
                "thumbnail_path": thumbnail_path,
                "status": "included",
                "added_by": "ai",
            })

        if not resolved_clips:
            raise ValueError("No valid clips after resolving paths")

        # Build clip pool (all detected actions NOT in the edit plan)
        selected_action_ids = {c.get("action_id") for c in resolved_clips}
        clip_pool = []
        for action in all_actions:
            if action["action_id"] in selected_action_ids:
                continue
            source_name = action.get("source_video", "")
            source_path = video_path_map.get(source_name, "")
            if not source_path:
                for name, path in video_path_map.items():
                    if source_name in name or name in source_name:
                        source_path = path
                        break

            # Thumbnail for pool clips
            thumb_path = None
            a_start = action.get("start_time", 0)
            a_end = action.get("end_time", 0)
            thumb_ts = a_start + ((a_end - a_start) * 0.33)
            for fr in all_frame_results:
                if os.path.basename(fr.video_path) == source_name:
                    closest_idx = min(
                        range(len(fr.frame_timestamps)),
                        key=lambda idx: abs(fr.frame_timestamps[idx] - thumb_ts),
                    )
                    thumb_path = fr.frame_paths[closest_idx]
                    break

            # Skip zero-duration actions
            if a_end <= a_start:
                continue

            clip_pool.append({
                "clip_id": str(uuid.uuid4()),
                "source_video": source_name,
                "source_path": source_path,
                "start_time": a_start,
                "end_time": a_end,
                "duration": a_end - a_start,
                "action_id": action["action_id"],
                "description": action.get("description", ""),
                "action_type": action.get("action_type", ""),
                "recipe_step": action.get("recipe_step"),
                "visual_quality": action.get("visual_quality", 0),
                "shows_action_moment": action.get("shows_action_moment", False),
                "thumbnail_path": thumb_path,
                "status": "excluded",
            })

        # Save edit plan to DB
        edit_plan_doc = {
            "_id": str(uuid.uuid4()),
            "project_id": project_id,
            "status": "draft",
            "version": 1,
            "timeline": {
                "clips": resolved_clips,
                "total_effective_duration": sum(c["effective_duration"] for c in resolved_clips),
                "target_duration": target_duration,
            },
            "clip_pool": clip_pool,
            "editor_notes": edit_result.get("editor_notes", ""),
            "coverage_pct": edit_result.get("coverage_pct"),
            "missing_steps": edit_result.get("missing_steps", []),
            "reconciliation": reconciliation,  # Recipe vs detected actions comparison
            "video_path_map": video_path_map,
            "history": [{
                "version": 1,
                "source": "ai",
                "action": "initial_generation",
                "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            }],
        }
        await db.edit_plans.insert_one(edit_plan_doc)

        # Also save edit decisions for backward compatibility
        for clip in resolved_clips:
            doc = {
                "_id": str(uuid.uuid4()),
                "project_id": project_id,
                "sequence_order": clip["order"],
                "action_id": clip.get("action_id"),
                "source_path": clip["source_path"],
                "start_time": clip["start_time"],
                "end_time": clip["end_time"],
                "duration": clip["duration"],
                "speed_factor": clip["speed_factor"],
                "recipe_step": clip.get("recipe_step"),
                "description": clip.get("description", ""),
                "reason": clip.get("reason", ""),
                "filename": clip.get("source_video", ""),
            }
            await db.edit_decisions.insert_one(doc)

        logger.info("Edit plan saved: %d clips in timeline, %d in pool",
                     len(resolved_clips), len(clip_pool))

        # ------------------------------------------------------------------ #
        # Step 4.4: Auto-select best thumbnail
        # ------------------------------------------------------------------ #
        await _update_project(db, project_id, ProjectStatus.SELECTING, 81,
                              "Selecting best thumbnail...")

        thumbnails_dir = os.path.join(settings.output_dir, "thumbnails")
        os.makedirs(thumbnails_dir, exist_ok=True)
        
        # Combine resolved clips + pool for thumbnail selection
        all_clips_for_thumbnails = resolved_clips + clip_pool
        
        best_thumbnail_path = await asyncio.to_thread(
            get_best_thumbnail_path,
            clips=all_clips_for_thumbnails,
            output_dir=thumbnails_dir,
            project_id=project_id,
        )
        
        if best_thumbnail_path:
            # Save thumbnail path to project
            thumbnail_filename = os.path.basename(best_thumbnail_path)
            await db.projects.update_one(
                {"_id": project_id},
                {"$set": {"thumbnail_path": f"/outputs/thumbnails/{thumbnail_filename}"}},
            )
            logger.info("Best thumbnail saved: %s", best_thumbnail_path)
        else:
            logger.warning("Failed to generate thumbnail for project %s", project_id)

        # ------------------------------------------------------------------ #
        # Step 4.5: Pre-render proxy clips (LEGO blocks)
        # ------------------------------------------------------------------ #
        await _update_project(db, project_id, ProjectStatus.STITCHING, 82,
                              f"Pre-rendering {len(resolved_clips) + len(clip_pool)} proxy clips...")

        # Combine timeline + pool for proxy rendering
        all_clips_for_proxy = resolved_clips + clip_pool
        proxies_dir = os.path.join(settings.upload_dir, project_id, "proxies")
        
        # Get aspect ratio from project (default to 16:9)
        aspect_ratio = project.get("aspect_ratio", "16:9")
        
        proxy_map = await pre_render_proxy_clips(
            project_id,
            all_clips_for_proxy,
            proxies_dir,
            db,
            aspect_ratio=aspect_ratio,
        )
        
        logger.info("Pre-rendered %d proxy clips for project %s", len(proxy_map), project_id)

        # ------------------------------------------------------------------ #
        # Step 4.6: Fast concat proxy preview
        # ------------------------------------------------------------------ #
        await _update_project(db, project_id, ProjectStatus.STITCHING, 84,
                              "Creating proxy preview...")

        timeline_clip_ids = [c["clip_id"] for c in sorted(resolved_clips, key=lambda x: x["order"])
                            if c.get("status") == "included"]
        
        proxy_preview_filename = f"{project_id}_proxy.mp4"
        proxy_preview_path = os.path.join(settings.output_dir, proxy_preview_filename)
        
        try:
            await fast_concat_proxies(timeline_clip_ids, proxy_map, proxy_preview_path, project_id)
            
            # Save proxy preview path in edit plan
            await db.edit_plans.update_one(
                {"project_id": project_id},
                {"$set": {"proxy_preview_path": proxy_preview_path}},
            )
            logger.info("Proxy preview created: %s", proxy_preview_path)
        except Exception as e:
            logger.warning("Failed to create proxy preview: %s", e)

        # ------------------------------------------------------------------ #
        # Step 5: Full HD render (still happens)
        # ------------------------------------------------------------------ #
        await _update_project(
            db, project_id, ProjectStatus.STITCHING, 86,
            f"Rendering HD video ({len(resolved_clips)} clips)...",
        )

        # Build stitch entries from edit plan
        stitch_entries = []
        for clip in sorted(resolved_clips, key=lambda c: c["order"]):
            if clip.get("status") != "included":
                continue
            stitch_entries.append({
                "source_path": clip["source_path"],
                "start_time": clip["start_time"],
                "end_time": clip["end_time"],
                "speed_factor": clip.get("speed_factor", 1.0),
            })

        if not stitch_entries:
            raise ValueError("No valid clips to stitch")

        output_filename = f"{project_id}_final.mp4"
        output_path = os.path.join(settings.output_dir, output_filename)

        # Get transition settings from project
        transition_type = project.get("transition_type", "fade")
        transition_duration = project.get("transition_duration", 0.5)
        
        # Render the video with aspect ratio and transitions
        await asyncio.to_thread(
            stitch_clips_v2, 
            stitch_entries, 
            output_path, 
            aspect_ratio,
            transition_type,
            transition_duration,
        )

        # Mark edit plan as completed
        await db.edit_plans.update_one(
            {"project_id": project_id},
            {"$set": {"status": "completed"}},
        )

        await _update_project(
            db, project_id, ProjectStatus.COMPLETED, 100, "Done!",
            output_path=output_path,
        )
        logger.info("Pipeline completed for project %s → %s (auto-rendered)", project_id, output_path)

    except Exception as exc:
        logger.exception("Pipeline failed for project %s", project_id)
        await _update_project(
            db, project_id, ProjectStatus.ERROR, 0,
            f"Error: {str(exc)[:200]}",
        )
