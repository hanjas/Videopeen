#!/usr/bin/env python3
"""Re-run clip selection + stitching without re-analyzing.

Usage:
    python scripts/reselect_stitch.py <project_id>
"""
import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings
from app.services.clip_selector import select_clips
from app.services.video_stitcher import stitch_clips
from app.models.project import ProjectStatus


async def main(project_id: str):
    client = AsyncIOMotorClient(settings.mongodb_uri)
    db = client[settings.mongodb_db]

    project = await db.projects.find_one({"_id": project_id})
    if not project:
        print(f"Project {project_id} not found")
        return

    # Load existing analyses
    analyses = await db.video_analyses.find({"project_id": project_id}).to_list(None)
    print(f"Found {len(analyses)} existing analyses")

    # Load chunk paths
    clips = await db.video_clips.find({"project_id": project_id}).to_list(None)
    chunk_size = project.get("chunk_size", 10)

    # Build chunk path mapping
    all_chunks = []
    for clip in clips:
        clip_id = clip["_id"]
        for seg in clip.get("segments", []):
            seg_dir = os.path.join(settings.upload_dir, project_id, "segments", clip_id)
            chunk_dir = os.path.join(seg_dir, f"chunks_{seg['index']}")
            if not os.path.exists(chunk_dir):
                continue
            # List chunk files
            chunk_files = sorted([f for f in os.listdir(chunk_dir) if f.endswith(('.mp4', '.mov', '.MOV'))])
            for ci, cf in enumerate(chunk_files):
                chunk_path = os.path.join(chunk_dir, cf)
                from app.services.video_processor import probe_duration
                dur = probe_duration(chunk_path)
                chunk_start = seg["start_time"] + ci * chunk_size
                chunk_end = seg["start_time"] + ci * chunk_size + dur
                all_chunks.append({
                    "clip_id": clip_id,
                    "segment_index": seg["index"],
                    "chunk_index": ci,
                    "start_time": chunk_start,
                    "end_time": chunk_end,
                    "path": chunk_path,
                })

    print(f"Found {len(all_chunks)} chunk files")

    # Re-run selection
    output_duration = project.get("output_duration", 60)
    decisions = select_clips(
        analyses,
        project.get("recipe_details", ""),
        project.get("dish_name", ""),
        project.get("instructions", ""),
        output_duration,
    )

    print(f"\nSelected {len(decisions)} clips:")
    for d in decisions:
        print(f"  [{d.sequence_order}] clip={d.source_clip_id[:8]} {d.start_time:.0f}-{d.end_time:.0f}s | {d.reason}")

    # Clear old decisions
    await db.edit_decisions.delete_many({"project_id": project_id})

    # Save new decisions and build stitch entries
    stitch_entries = []
    for decision in decisions:
        decision.project_id = project_id
        doc = decision.model_dump(by_alias=True, exclude_none=True)
        doc["_id"] = str(uuid.uuid4())
        await db.edit_decisions.insert_one(doc)

        matching_chunk = min(
            (c for c in all_chunks if c["clip_id"] == decision.source_clip_id),
            key=lambda c: abs(c["start_time"] - decision.start_time),
            default=None,
        )
        if matching_chunk:
            chunk_dur = matching_chunk["end_time"] - matching_chunk["start_time"]
            stitch_entries.append({
                "source_path": matching_chunk["path"],
                "start_time": 0.0,
                "end_time": chunk_dur,
            })

    # Stitch
    output_path = os.path.join(settings.output_dir, f"{project_id}_final.mp4")
    print(f"\nStitching {len(stitch_entries)} clips to {output_path}...")
    stitch_clips(stitch_entries, output_path)

    await db.projects.update_one(
        {"_id": project_id},
        {"$set": {"status": ProjectStatus.COMPLETED.value, "output_path": output_path}}
    )

    from app.services.video_processor import probe_duration as pd
    final_dur = pd(output_path)
    print(f"Done! Output: {output_path} ({final_dur:.1f}s)")

    client.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/reselect_stitch.py <project_id>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
