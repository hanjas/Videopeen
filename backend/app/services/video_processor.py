"""Video processing: dense frame extraction for action-based analysis.

V3 Architecture: Extract 1 frame every 2 seconds from full video.
No chunking, no scene detection — let Claude identify actions from the temporal flow.

V3.1: Motion-based frame filtering to reduce redundant frames by 50-70%.
V3.2: SSIM-based scene selection at 2fps, keeping all frames in brief scenes (<2s).
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
    frame_interval: float = 0.5  # seconds between frames (changed to 2fps)
    total_extracted: int = 0     # Before filtering
    total_filtered: int = 0      # After filtering
    scene_count: int = 0         # Number of scenes detected
    frames_before_selection: int = 0  # Frames before scene selection


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


def compute_ssim_cv2(img1: np.ndarray, img2: np.ndarray) -> float:
    """Compute SSIM between two grayscale images using OpenCV.
    
    Args:
        img1: First image (grayscale)
        img2: Second image (grayscale)
    
    Returns:
        SSIM score (0.0-1.0, higher = more similar)
    """
    C1 = (0.01 * 255) ** 2
    C2 = (0.03 * 255) ** 2
    
    img1 = img1.astype(np.float64)
    img2 = img2.astype(np.float64)
    
    mu1 = cv2.GaussianBlur(img1, (11, 11), 1.5)
    mu2 = cv2.GaussianBlur(img2, (11, 11), 1.5)
    
    mu1_sq = mu1 ** 2
    mu2_sq = mu2 ** 2
    mu1_mu2 = mu1 * mu2
    
    sigma1_sq = cv2.GaussianBlur(img1 ** 2, (11, 11), 1.5) - mu1_sq
    sigma2_sq = cv2.GaussianBlur(img2 ** 2, (11, 11), 1.5) - mu2_sq
    sigma12 = cv2.GaussianBlur(img1 * img2, (11, 11), 1.5) - mu1_mu2
    
    ssim_map = ((2 * mu1_mu2 + C1) * (2 * sigma12 + C2)) / \
               ((mu1_sq + mu2_sq + C1) * (sigma1_sq + sigma2_sq + C2))
    
    return float(np.mean(ssim_map))


def is_scene_break(
    prev_img: np.ndarray,
    curr_img: np.ndarray,
    threshold: float,
) -> bool:
    """Determine if there's a scene break between two frames using two-signal gate.
    
    Args:
        prev_img: Previous frame (256x256 grayscale)
        curr_img: Current frame (256x256 grayscale)
        threshold: SSIM threshold for scene break
    
    Returns:
        True if scene break detected
    """
    full_ssim = compute_ssim_cv2(prev_img, curr_img)
    
    if full_ssim > threshold:
        return False  # Clearly same scene
    
    if full_ssim < threshold - 0.10:
        return True  # Clearly different scene
    
    # Ambiguous: check center crop (wobble affects edges, not center)
    h, w = prev_img.shape
    crop_h, crop_w = int(h * 0.5), int(w * 0.5)
    start_h, start_w = (h - crop_h) // 2, (w - crop_w) // 2
    
    prev_center = prev_img[start_h:start_h + crop_h, start_w:start_w + crop_w]
    curr_center = curr_img[start_h:start_h + crop_h, start_w:start_w + crop_w]
    
    center_ssim = compute_ssim_cv2(prev_center, curr_center)
    return center_ssim < threshold


def select_frames_by_scene(
    frame_paths: list[str],
    frame_timestamps: list[float],
    ssim_threshold: float = 0.90,
) -> tuple[list[str], list[float], int]:
    """Select frames using SSIM-based scene segmentation.
    
    Key rule: brief scenes (<2s) keep ALL frames.
    This inverts the motion filter's behavior where brief actions get dropped.
    
    Args:
        frame_paths: All extracted frame paths
        frame_timestamps: Corresponding timestamps
        ssim_threshold: Scene break threshold (adaptive per video)
    
    Returns:
        (selected_paths, selected_timestamps, scene_count)
    """
    if not frame_paths:
        return [], [], 0
    
    if len(frame_paths) == 1:
        return frame_paths, frame_timestamps, 1
    
    logger.info("SSIM scene selection: processing %d frames", len(frame_paths))
    
    # Load and downsample all frames to 256x256 grayscale for fast SSIM
    frames = []
    valid_indices = []
    
    for i, path in enumerate(frame_paths):
        try:
            img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            if img is None:
                logger.warning("Failed to load frame %s, skipping", path)
                continue
            # Downsample to 256x256
            img_small = cv2.resize(img, (256, 256))
            frames.append(img_small)
            valid_indices.append(i)
        except Exception as e:
            logger.warning("Error loading frame %s: %s", path, e)
    
    if len(frames) <= 1:
        return frame_paths, frame_timestamps, 1
    
    # Compute pairwise SSIM between consecutive frames
    ssim_scores = []
    for i in range(len(frames) - 1):
        ssim_score = compute_ssim_cv2(frames[i], frames[i + 1])
        ssim_scores.append(ssim_score)
    
    # Compute adaptive threshold: max(0.85, median(all_ssim) - 0.05)
    median_ssim = float(np.median(ssim_scores))
    adaptive_threshold = max(0.85, median_ssim - 0.05)
    logger.info("SSIM adaptive threshold: %.3f (median: %.3f)", adaptive_threshold, median_ssim)
    
    # Detect scene breaks using two-signal gate
    scene_breaks = [0]  # First frame is always a scene start
    
    for i in range(len(frames) - 1):
        if is_scene_break(frames[i], frames[i + 1], adaptive_threshold):
            scene_breaks.append(i + 1)
            logger.debug("Scene break detected at frame %d (SSIM: %.3f)", i + 1, ssim_scores[i])
    
    scene_breaks.append(len(frames))  # Add end marker
    
    num_scenes = len(scene_breaks) - 1
    logger.info("Detected %d scenes", num_scenes)
    
    # Select frames per scene
    selected_indices = set()
    frames_to_delete = []
    
    for scene_idx in range(num_scenes):
        scene_start = scene_breaks[scene_idx]
        scene_end = scene_breaks[scene_idx + 1]
        scene_frame_indices = list(range(scene_start, scene_end))
        
        if not scene_frame_indices:
            continue
        
        # Map back to original indices
        original_start_idx = valid_indices[scene_start]
        original_end_idx = valid_indices[scene_end - 1]
        
        scene_duration = frame_timestamps[original_end_idx] - frame_timestamps[original_start_idx]
        scene_frames = scene_end - scene_start
        
        logger.debug("Scene %d: %.1fs, %d frames", scene_idx, scene_duration, scene_frames)
        
        # Scene selection logic
        if scene_duration < 2.0:
            # Brief scene: KEEP ALL FRAMES
            for idx in scene_frame_indices:
                selected_indices.add(valid_indices[idx])
            logger.debug("Scene %d: brief (%.1fs), keeping all %d frames", 
                        scene_idx, scene_duration, scene_frames)
        
        elif scene_duration < 5.0:
            # Medium scene: keep first, middle, last
            keep_indices = [
                scene_frame_indices[0],
                scene_frame_indices[len(scene_frame_indices) // 2],
                scene_frame_indices[-1],
            ]
            for idx in keep_indices:
                selected_indices.add(valid_indices[idx])
            logger.debug("Scene %d: medium (%.1fs), keeping 3 frames (first, middle, last)",
                        scene_idx, scene_duration)
        
        else:
            # Long scene: keep first + last + 1 per 4s interior
            selected_indices.add(valid_indices[scene_frame_indices[0]])
            selected_indices.add(valid_indices[scene_frame_indices[-1]])
            
            # Interior frames: 1 per 4s
            interior_frames = scene_frame_indices[1:-1]
            if interior_frames:
                frames_per_4s = max(1, int(scene_duration / 4.0))
                step = max(1, len(interior_frames) // frames_per_4s)
                for i in range(0, len(interior_frames), step):
                    selected_indices.add(valid_indices[interior_frames[i]])
            
            logger.debug("Scene %d: long (%.1fs), keeping first + last + %d interior",
                        scene_idx, scene_duration, len([i for i in interior_frames[::step]]))
        
        # Always keep frames at scene boundaries
        if scene_idx > 0:
            # Keep last frame of previous scene and first frame of this scene
            selected_indices.add(valid_indices[scene_breaks[scene_idx] - 1])
            selected_indices.add(valid_indices[scene_breaks[scene_idx]])
    
    # Build result lists
    selected_paths = []
    selected_timestamps = []
    
    for i, (path, ts) in enumerate(zip(frame_paths, frame_timestamps)):
        if i in selected_indices:
            selected_paths.append(path)
            selected_timestamps.append(ts)
        else:
            frames_to_delete.append(path)
    
    # Delete unselected frames
    for path in frames_to_delete:
        try:
            os.remove(path)
            logger.debug("Deleted redundant frame: %s", path)
        except Exception as e:
            logger.warning("Failed to delete frame %s: %s", path, e)
    
    compression_ratio = (1 - len(selected_paths) / len(frame_paths)) * 100
    logger.info("SSIM scene selection: %d scenes detected, %d/%d frames kept (%.1f%% compression)",
                num_scenes, len(selected_paths), len(frame_paths), compression_ratio)
    
    return selected_paths, selected_timestamps, num_scenes


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
    frame_interval: float = 0.5,
    target_long_side: int = 768,
    video_index: int = 0,
    motion_filter: bool = False,  # Deprecated, kept for compatibility
) -> DenseFrameResult:
    """Extract frames at 2fps (0.5s interval) then apply SSIM scene selection.
    
    V3.2: Extracts at 2fps then applies SSIM-based scene selection.
    Brief scenes (<2s) keep ALL frames to preserve action details.
    
    Args:
        video_path: Path to source video
        output_dir: Directory to save extracted frames
        frame_interval: Extraction interval in seconds (default 0.5 = 2fps)
        target_long_side: Max dimension for extracted frames
        video_index: Index for naming (when processing multiple videos)
        motion_filter: Deprecated (kept for compatibility, SSIM always used)
    
    Returns:
        DenseFrameResult with paths and timestamps
    """
    if motion_filter:
        logger.warning("motion_filter parameter is deprecated, using SSIM scene selection")
    
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    duration = get_video_duration(video_path)
    
    # V3.2: Extract at 2fps (0.5s interval)
    extraction_fps = 1.0 / frame_interval
    logger.info("Extracting dense frames from %s (%.1fs at %.1f fps)",
                os.path.basename(video_path), duration, extraction_fps)
    
    # Calculate expected frames
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
            timestamp = (i - 1) / extraction_fps
            if timestamp <= duration + (1.0 / extraction_fps):
                frame_paths.append(path)
                frame_timestamps.append(timestamp)
        else:
            break
    
    total_extracted = len(frame_paths)
    logger.info("Extracted %d frames from %s (%.1fs)", 
                total_extracted, os.path.basename(video_path), duration)
    
    # Apply SSIM scene selection
    if total_extracted > 1:
        filtered_paths, filtered_timestamps, scene_count = select_frames_by_scene(
            frame_paths,
            frame_timestamps,
            ssim_threshold=0.90,
        )
        total_filtered = len(filtered_paths)
    else:
        filtered_paths = frame_paths
        filtered_timestamps = frame_timestamps
        total_filtered = total_extracted
        scene_count = 1
    
    return DenseFrameResult(
        video_path=video_path,
        total_duration=duration,
        frame_paths=filtered_paths,
        frame_timestamps=filtered_timestamps,
        frame_interval=frame_interval,
        total_extracted=total_extracted,
        total_filtered=total_filtered,
        scene_count=scene_count,
        frames_before_selection=total_extracted,
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
