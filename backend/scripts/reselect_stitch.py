#!/usr/bin/env python3
"""Re-run clip selection and stitching using existing analyses (skips slow VL analysis)."""
import asyncio
import os
import sys
import json

# Add parent to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from motor.motor_asyncio import AsyncIOMotorClient
from app.services.clip_selector import select_clips
from app.services.video_stitcher import stitch_clips
from app.config import settings

PROJECT_ID = sys.argv[1] if len(sys.argv) > 1 else None
if not PROJECT_ID:
    print("Usage: python scripts/reselect_stitch.py <project_id>")
    sys.exit(1)


async def main():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client[settings.mongodb_db]

    project = await db.projects.find_one({"_id": PROJECT_ID})
    if not project:
        print(f"Project {PROJECT_ID} not found")
        sys.exit(1)

    # Get existing analyses
    analyses = await db.video_analyses.find({"project_id": PROJECT_ID}).to_list(None)
    print(f"Found {len(analyses)} existing analyses")

    # Get clips for chunk path resolution
    clips = await db.video_clips.find({"project_id": PROJECT_ID}).to_list(None)
    
    # Build chunk paths from segments
    all_chunks = []
    for clip in clips:
        clip_id = clip["_id"]
        for seg in clip.get("segments", []):
            seg_dir = os.path.join(settings.upload_dir, PROJECT_ID, "segments", clip_id)
            chunk_dir = os.path.join(seg_dir, f"chunks_{seg['index']}")
            if not os.path.exists(chunk_dir):
                continue
            chunk_files = sorted([f for f in os.listdir(chunk_dir) if f.endswith(('.mp4', '.mov', '.MOV'))])
            for chunk_idx, fname in enumerate(chunk_files):
                chunk_path = os.path.join(chunk_dir, fname)
                for a in analyses:
                    if (a["clip_id"] == clip_id and 
                        a.get("segment_index") == seg["index"] and
                        a.get("chunk_index") == chunk_idx):
                        all_chunks.append({
                            "clip_id": clip_id,
                            "segment_index": seg["index"],
                            "chunk_index": chunk_idx,
                            "start_time": a["start_time"],
                            "end_time": a["end_time"],
                            "path": chunk_path,
                        })
                        break

    print(f"Found {len(all_chunks)} chunk files")

    # Clear old decisions
    await db.edit_decisions.delete_many({"project_id": PROJECT_ID})

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
    stitch_entries = []
    for d in decisions:
        d.project_id = PROJECT_ID
        print(f"  Order {d.sequence_order}: clip={d.source_clip_id[:8]}... t={d.start_time:.0f}-{d.end_time:.0f} - {d.reason}")
        
        # Find matching chunk
        matching = min(
            (c for c in all_chunks if c["clip_id"] == d.source_clip_id),
            key=lambda c: abs(c["start_time"] - d.start_time),
            default=None,
        )
        if matching:
            chunk_dur = matching["end_time"] - matching["start_time"]
            stitch_entries.append({
                "source_path": matching["path"],
                "start_time": 0.0,
                "end_time": chunk_dur,
            })

    # Stitch
    output_path = os.path.join(settings.output_dir, f"{PROJECT_ID}_final.mp4")
    print(f"\nStitching {len(stitch_entries)} clips to {output_path}...")
    stitch_clips(stitch_entries, output_path)

    # Update project
    await db.projects.update_one({"_id": PROJECT_ID}, {"$set": {
        "status": "completed",
        "output_path": output_path,
        "progress": 100,
        "current_step": "Done (reselected)!",
    }})

    print(f"Done! Output: {output_path}")
    client.close()


asyncio.run(main())
