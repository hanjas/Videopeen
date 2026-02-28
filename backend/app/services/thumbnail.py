"""Thumbnail generation service — select and extract best frames from videos."""

from __future__ import annotations

import logging
import os
import subprocess
from typing import Any

logger = logging.getLogger(__name__)


def select_best_thumbnails(
    clips: list[dict[str, Any]],
    top_n: int = 3,
) -> list[dict[str, Any]]:
    """Select top N clips with highest visual quality for thumbnails.
    
    Args:
        clips: List of clip dictionaries with visual_quality scores
        top_n: Number of top thumbnails to select (default: 3)
    
    Returns:
        List of selected clips sorted by visual quality (highest first)
    """
    # Filter clips with visual_quality scores
    scored_clips = [
        c for c in clips
        if c.get("visual_quality") is not None
    ]
    
    if not scored_clips:
        logger.warning("No clips with visual_quality scores found")
        return []
    
    # Sort by visual quality (highest first)
    sorted_clips = sorted(
        scored_clips,
        key=lambda c: c.get("visual_quality", 0),
        reverse=True
    )
    
    # Return top N
    return sorted_clips[:top_n]


def extract_frame_from_video(
    video_path: str,
    timestamp: float,
    output_path: str,
    width: int = 1920,
) -> bool:
    """Extract a single frame from video at specified timestamp using ffmpeg.
    
    Args:
        video_path: Path to source video file
        timestamp: Time in seconds to extract frame
        output_path: Path to save the frame (JPG)
        width: Target width (maintains aspect ratio)
    
    Returns:
        True if successful, False otherwise
    """
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Build ffmpeg command
        cmd = [
            "ffmpeg",
            "-y",  # Overwrite output file
            "-ss", str(timestamp),  # Seek to timestamp
            "-i", video_path,
            "-vframes", "1",  # Extract 1 frame
            "-vf", f"scale={width}:-2",  # Scale to width, maintain aspect ratio
            "-q:v", "2",  # High quality JPEG (2 = excellent quality)
            output_path,
        ]
        
        logger.info(
            "Extracting frame from %s at %.1fs → %s",
            os.path.basename(video_path),
            timestamp,
            output_path
        )
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        if result.returncode != 0:
            logger.error("ffmpeg failed: %s", result.stderr)
            return False
        
        if not os.path.exists(output_path):
            logger.error("Output file not created: %s", output_path)
            return False
        
        logger.info("Frame extracted successfully: %s (%.1f KB)",
                   output_path, os.path.getsize(output_path) / 1024)
        return True
        
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg timeout extracting frame from %s", video_path)
        return False
    except Exception as e:
        logger.exception("Failed to extract frame: %s", e)
        return False


def generate_thumbnails_from_clips(
    clips: list[dict[str, Any]],
    output_dir: str,
    project_id: str,
    top_n: int = 3,
) -> list[dict[str, Any]]:
    """Generate top N thumbnails from clips based on visual quality.
    
    This extracts frames at full resolution from the source videos.
    
    Args:
        clips: List of clip/action dictionaries with visual_quality scores
        output_dir: Directory to save thumbnails
        project_id: Project ID for naming files
        top_n: Number of thumbnails to generate (default: 3)
    
    Returns:
        List of thumbnail info dicts with paths and metadata
    """
    # Select best clips
    best_clips = select_best_thumbnails(clips, top_n)
    
    if not best_clips:
        logger.warning("No clips selected for thumbnail generation")
        return []
    
    thumbnails = []
    
    for i, clip in enumerate(best_clips):
        # Determine timestamp to extract
        # Prefer key_frame_timestamp if available, otherwise use mid-point
        start = clip.get("start_time", 0)
        end = clip.get("end_time", 0)
        
        if clip.get("key_frame_timestamp") is not None:
            timestamp = clip["key_frame_timestamp"]
        else:
            # Use 33% mark (visually appealing moment, not dead center)
            timestamp = start + (end - start) * 0.33
        
        # Build output path
        thumbnail_filename = f"{project_id}_thumb_{i+1}.jpg"
        thumbnail_path = os.path.join(output_dir, thumbnail_filename)
        
        # Skip if thumbnail already exists
        if os.path.exists(thumbnail_path):
            logger.info("Thumbnail already exists: %s", thumbnail_path)
            thumbnails.append({
                "rank": i + 1,
                "path": thumbnail_path,
                "timestamp": timestamp,
                "visual_quality": clip.get("visual_quality", 0),
                "description": clip.get("description", ""),
                "source_video": clip.get("source_video", ""),
            })
            continue
        
        # Extract frame from source video
        source_path = clip.get("source_path", "")
        
        if not source_path or not os.path.exists(source_path):
            logger.warning(
                "Source video not found for clip: %s",
                clip.get("source_video", "unknown")
            )
            continue
        
        success = extract_frame_from_video(
            video_path=source_path,
            timestamp=timestamp,
            output_path=thumbnail_path,
            width=1920,  # Full HD width
        )
        
        if success:
            thumbnails.append({
                "rank": i + 1,
                "path": thumbnail_path,
                "timestamp": timestamp,
                "visual_quality": clip.get("visual_quality", 0),
                "description": clip.get("description", ""),
                "source_video": clip.get("source_video", ""),
            })
    
    logger.info("Generated %d thumbnails for project %s", len(thumbnails), project_id)
    return thumbnails


def get_best_thumbnail_path(
    clips: list[dict[str, Any]],
    output_dir: str,
    project_id: str,
) -> str | None:
    """Get the path to the single best thumbnail for a project.
    
    This is used in pipeline.py to auto-select the best thumbnail.
    
    Args:
        clips: List of clips with visual_quality scores
        output_dir: Directory to save thumbnail
        project_id: Project ID
    
    Returns:
        Path to best thumbnail, or None if generation failed
    """
    thumbnails = generate_thumbnails_from_clips(
        clips=clips,
        output_dir=output_dir,
        project_id=project_id,
        top_n=1,  # Only need the best one
    )
    
    if thumbnails:
        return thumbnails[0]["path"]
    
    return None
