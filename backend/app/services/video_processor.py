"""Video processing: dense frame extraction for action-based analysis.

V3 Architecture: Extract 1 frame every 2 seconds from full video.
No chunking, no scene detection — let Claude identify actions from the temporal flow.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class DenseFrameResult:
    """Result of dense frame extraction for one video."""
    video_path: str
    total_duration: float
    frame_paths: list[str] = field(default_factory=list)
    frame_timestamps: list[float] = field(default_factory=list)
    frame_interval: float = 2.0  # seconds between frames


def get_video_duration(video_path: str) -> float:
    """Get video duration using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr[:200]}")
    return float(result.stdout.strip())


def extract_dense_frames(
    video_path: str,
    output_dir: str,
    frame_interval: float = 2.0,
    target_long_side: int = 768,
    video_index: int = 0,
) -> DenseFrameResult:
    """Extract 1 frame every `frame_interval` seconds from full video.
    
    Args:
        video_path: Path to source video
        output_dir: Directory to save extracted frames
        frame_interval: Seconds between frames (default 2.0)
        target_long_side: Max dimension for extracted frames
        video_index: Index for naming (when processing multiple videos)
    
    Returns:
        DenseFrameResult with paths and timestamps
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    duration = get_video_duration(video_path)
    logger.info("Extracting dense frames from %s (%.1fs, 1 frame every %.1fs)",
                os.path.basename(video_path), duration, frame_interval)
    
    # Calculate expected frames
    n_frames = max(1, int(duration / frame_interval))
    
    # Use ffmpeg to extract frames at regular intervals
    # Scale to target_long_side while maintaining aspect ratio
    scale_filter = (
        f"scale='if(gt(iw,ih),{target_long_side},-2)':'if(gt(iw,ih),-2,{target_long_side})'"
    )
    
    frame_paths = []
    frame_timestamps = []
    
    # Extract all frames in one ffmpeg call using fps filter
    pattern = os.path.join(output_dir, f"v{video_index:02d}_frame_%04d.jpg")
    fps_value = 1.0 / frame_interval
    
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"fps={fps_value},{scale_filter}:flags=fast_bilinear",
        "-q:v", "4",  # Good quality JPEG
        "-vsync", "vfr",
        pattern,
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("Dense frame extraction failed: %s", result.stderr[:300])
        raise RuntimeError(f"Frame extraction failed for {video_path}")
    
    # Collect generated frames
    for i in range(1, n_frames + 10):  # +10 buffer for rounding
        path = os.path.join(output_dir, f"v{video_index:02d}_frame_{i:04d}.jpg")
        if os.path.exists(path):
            timestamp = (i - 1) * frame_interval
            if timestamp <= duration + frame_interval:
                frame_paths.append(path)
                frame_timestamps.append(timestamp)
        else:
            break
    
    logger.info("Extracted %d frames from %s (%.1fs)", 
                len(frame_paths), os.path.basename(video_path), duration)
    
    return DenseFrameResult(
        video_path=video_path,
        total_duration=duration,
        frame_paths=frame_paths,
        frame_timestamps=frame_timestamps,
        frame_interval=frame_interval,
    )


# Keep legacy exports for compatibility
@dataclass
class SceneInfo:
    """Legacy compat — not used in V3 pipeline."""
    index: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
    source_video: str = ""
    clip_id: str = ""
    scene_type: str = ""
    duplicate_group: int = -1
    motion_score: float = 0.0
    keyframe_paths: list[str] = field(default_factory=list)
    keyframe_timestamps: list[float] = field(default_factory=list)


@dataclass
class PreprocessResult:
    """Legacy compat."""
    scenes: list[SceneInfo] = field(default_factory=list)
    total_duration: float = 0.0
