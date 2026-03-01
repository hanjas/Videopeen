"""Video processing: dense frame extraction for action-based analysis.

V3 Architecture: Extract 1 frame every 2 seconds from full video.
No chunking, no scene detection — let Claude identify actions from the temporal flow.

V3.1: Motion-based frame filtering to reduce redundant frames by 50-70%.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class DenseFrameResult:
    """Result of dense frame extraction for one video."""
    video_path: str
    total_duration: float
    frame_paths: list[str] = field(default_factory=list)
    frame_timestamps: list[float] = field(default_factory=list)
    frame_interval: float = 1.0  # seconds between frames (changed from 2.0)
    total_extracted: int = 0     # Before filtering
    total_filtered: int = 0      # After filtering


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


def filter_frames_by_motion(
    frame_paths: list[str],
    frame_timestamps: list[float],
    diff_threshold: float = 0.03,      # 3% pixel difference = "changed"
    min_interval: float = 2.0,          # Never skip more than this many seconds
    max_interval: float = 10.0,         # Always keep at least 1 frame per this many seconds
    always_keep_first_last: bool = True, # Always keep first and last frames
) -> tuple[list[str], list[float]]:
    """Filter extracted frames, keeping only those with significant visual change.
    
    Algorithm:
    1. Compare each frame to the last KEPT frame using structural similarity
    2. If difference > threshold → KEEP (something changed)
    3. If time since last kept frame > max_interval → KEEP (safety net)
    4. If difference < threshold AND time < max_interval → SKIP (redundant)
    5. Always keep first and last frames
    
    Args:
        frame_paths: List of extracted frame file paths
        frame_timestamps: Corresponding timestamps (seconds)
        diff_threshold: Minimum normalized difference to consider frame changed (0.0-1.0)
        min_interval: Minimum seconds between frames (legacy compat)
        max_interval: Maximum seconds between frames (safety net)
        always_keep_first_last: Always keep first and last frames
    
    Returns:
        Tuple of (filtered_frame_paths, filtered_frame_timestamps)
    """
    if not frame_paths:
        return [], []
    
    if len(frame_paths) == 1:
        return frame_paths, frame_timestamps
    
    kept_paths = []
    kept_timestamps = []
    frames_to_delete = []
    
    # Always keep first frame
    kept_paths.append(frame_paths[0])
    kept_timestamps.append(frame_timestamps[0])
    last_kept_idx = 0
    last_kept_frame = None
    
    # Load and prepare first frame for comparison
    try:
        img = cv2.imread(frame_paths[0])
        if img is not None:
            last_kept_frame = cv2.resize(img, (160, 120))
    except Exception as e:
        logger.warning("Failed to load first frame for motion filter: %s", e)
    
    # Process remaining frames
    for i in range(1, len(frame_paths)):
        current_path = frame_paths[i]
        current_ts = frame_timestamps[i]
        time_since_last = current_ts - kept_timestamps[-1]
        
        # Safety net: always keep if too much time passed
        if time_since_last >= max_interval:
            kept_paths.append(current_path)
            kept_timestamps.append(current_ts)
            last_kept_idx = i
            try:
                img = cv2.imread(current_path)
                if img is not None:
                    last_kept_frame = cv2.resize(img, (160, 120))
            except Exception as e:
                logger.warning("Failed to load frame %s: %s", current_path, e)
            continue
        
        # Compare to last kept frame
        keep_frame = False
        if last_kept_frame is None:
            # Can't compare, keep by default
            keep_frame = True
        else:
            try:
                current_img = cv2.imread(current_path)
                if current_img is None:
                    logger.warning("Failed to load frame %s, keeping by default", current_path)
                    keep_frame = True
                else:
                    # Resize for fast comparison
                    current_small = cv2.resize(current_img, (160, 120))
                    
                    # Calculate pixel difference
                    diff = cv2.absdiff(last_kept_frame, current_small)
                    diff_score = np.mean(diff) / 255.0
                    
                    # Keep if difference exceeds threshold
                    if diff_score > diff_threshold:
                        keep_frame = True
                        logger.debug("Frame %d: diff=%.4f > %.4f, KEEP", i, diff_score, diff_threshold)
                    else:
                        logger.debug("Frame %d: diff=%.4f ≤ %.4f, SKIP", i, diff_score, diff_threshold)
            except Exception as e:
                logger.warning("Motion comparison failed for %s: %s, keeping by default", current_path, e)
                keep_frame = True
        
        if keep_frame:
            kept_paths.append(current_path)
            kept_timestamps.append(current_ts)
            last_kept_idx = i
            try:
                img = cv2.imread(current_path)
                if img is not None:
                    last_kept_frame = cv2.resize(img, (160, 120))
            except Exception:
                pass
        else:
            frames_to_delete.append(current_path)
    
    # Always keep last frame if requested and not already kept
    if always_keep_first_last and frame_paths[-1] not in kept_paths:
        # Remove from delete list if it was marked for deletion
        if frame_paths[-1] in frames_to_delete:
            frames_to_delete.remove(frame_paths[-1])
        kept_paths.append(frame_paths[-1])
        kept_timestamps.append(frame_timestamps[-1])
    
    # Delete redundant frames from disk
    for path in frames_to_delete:
        try:
            os.remove(path)
            logger.debug("Deleted redundant frame: %s", path)
        except Exception as e:
            logger.warning("Failed to delete frame %s: %s", path, e)
    
    logger.info("Motion filter: kept %d/%d frames (%.1f%% reduction), deleted %d redundant",
                len(kept_paths), len(frame_paths),
                (1 - len(kept_paths) / len(frame_paths)) * 100,
                len(frames_to_delete))
    
    return kept_paths, kept_timestamps


def extract_dense_frames(
    video_path: str,
    output_dir: str,
    frame_interval: float = 2.0,
    target_long_side: int = 768,
    video_index: int = 0,
    motion_filter: bool = True,
) -> DenseFrameResult:
    """Extract 1 frame every `frame_interval` seconds from full video.
    
    V3.1: Now extracts at 1fps then applies motion filtering to remove redundant frames.
    
    Args:
        video_path: Path to source video
        output_dir: Directory to save extracted frames
        frame_interval: Minimum seconds between frames (used for motion filter, default 2.0)
        target_long_side: Max dimension for extracted frames
        video_index: Index for naming (when processing multiple videos)
        motion_filter: Enable motion-based filtering (default True)
    
    Returns:
        DenseFrameResult with paths and timestamps
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    duration = get_video_duration(video_path)
    
    # V3.1: Extract at 1fps for motion analysis, then filter
    extraction_fps = 1.0
    logger.info("Extracting dense frames from %s (%.1fs at %.1f fps)",
                os.path.basename(video_path), duration, extraction_fps)
    
    # Calculate expected frames at 1fps
    n_frames = max(1, int(duration * extraction_fps))
    
    # Use ffmpeg to extract frames at regular intervals
    # Scale to target_long_side while maintaining aspect ratio
    scale_filter = (
        f"scale='if(gt(iw,ih),{target_long_side},-2)':'if(gt(iw,ih),-2,{target_long_side})'"
    )
    
    frame_paths = []
    frame_timestamps = []
    
    # Extract all frames in one ffmpeg call using fps filter
    pattern = os.path.join(output_dir, f"v{video_index:02d}_frame_%04d.jpg")
    fps_value = extraction_fps
    
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
            timestamp = (i - 1) / extraction_fps  # 1fps extraction
            if timestamp <= duration + (1.0 / extraction_fps):
                frame_paths.append(path)
                frame_timestamps.append(timestamp)
        else:
            break
    
    total_extracted = len(frame_paths)
    logger.info("Extracted %d frames from %s (%.1fs)", 
                total_extracted, os.path.basename(video_path), duration)
    
    # Apply motion filtering
    if motion_filter and total_extracted > 1:
        filtered_paths, filtered_timestamps = filter_frames_by_motion(
            frame_paths, 
            frame_timestamps,
            diff_threshold=0.03,
            min_interval=frame_interval,
            max_interval=8.0,
        )
        total_filtered = len(filtered_paths)
    else:
        filtered_paths = frame_paths
        filtered_timestamps = frame_timestamps
        total_filtered = total_extracted
    
    return DenseFrameResult(
        video_path=video_path,
        total_duration=duration,
        frame_paths=filtered_paths,
        frame_timestamps=filtered_timestamps,
        frame_interval=frame_interval,
        total_extracted=total_extracted,
        total_filtered=total_filtered,
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
