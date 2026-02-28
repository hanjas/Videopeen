"""Stitch selected clips into final output video with speed ramps."""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def stitch_clips_v2(
    clip_entries: list[dict],
    output_path: str,
    aspect_ratio: str = "16:9",
) -> str:
    """Stitch clips with speed ramps using ffmpeg filter_complex.
    
    Each entry has:
        - source_path: path to source video
        - start_time: float seconds
        - end_time: float seconds
        - speed_factor: float (1.0 = normal, 2.0 = 2x speed, 0.75 = slow-mo)
    
    Args:
        clip_entries: List of clip dictionaries with timing and source info
        output_path: Output file path
        aspect_ratio: Target aspect ratio - "16:9" (default), "9:16" (vertical), or "1:1" (square)
    """
    if not clip_entries:
        raise ValueError("No clips to stitch")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Group clips by source file to minimize inputs
    # For simplicity, use one input per source and trim with filter
    # Build the filter_complex string

    # Deduplicate source paths
    source_paths = list(dict.fromkeys(e["source_path"] for e in clip_entries))
    source_index = {path: i for i, path in enumerate(source_paths)}

    filter_parts = []
    concat_inputs = []

    for i, entry in enumerate(clip_entries):
        src_idx = source_index[entry["source_path"]]
        start = entry["start_time"]
        end = entry["end_time"]
        speed = entry.get("speed_factor", 1.0)
        duration = end - start

        if duration <= 0:
            continue

        # Trim video and normalize pixel format for consistent concat
        trim_filter = f"[{src_idx}:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS,setsar=1,format=yuv420p"

        # Apply speed change if needed
        if speed != 1.0 and speed > 0:
            trim_filter += f",setpts={1.0/speed:.4f}*PTS"

        trim_filter += f"[v{i}]"
        filter_parts.append(trim_filter)
        concat_inputs.append(f"[v{i}]")

    if not concat_inputs:
        raise ValueError("No valid clips after filtering")

    # Concat all clips
    n = len(concat_inputs)
    concat_filter = "".join(concat_inputs) + f"concat=n={n}:v=1:a=0[concat]"
    filter_parts.append(concat_filter)
    
    # Apply aspect ratio crop/scale AFTER concat
    # Source videos are typically 1080x1920 (portrait) after auto-rotation
    # Crop is centered using (iw-crop_w)/2 and (ih-crop_h)/2
    if aspect_ratio == "9:16":
        # Vertical (TikTok/Reels/Shorts): 1080x1920
        # Crop to 9:16 aspect ratio, centered
        crop_filter = (
            "[concat]crop="
            "w='min(iw,ih*9/16)':"  # width: either full width or height*9/16
            "h='min(ih,iw*16/9)':"  # height: either full height or width*16/9
            "x='(iw-min(iw,ih*9/16))/2':"  # center horizontally
            "y='(ih-min(ih,iw*16/9))/2',"  # center vertically
            "scale=1080:1920[outv]"
        )
        filter_parts.append(crop_filter)
    elif aspect_ratio == "1:1":
        # Square (Instagram feed): 1080x1080
        # Crop to square, centered
        crop_filter = (
            "[concat]crop="
            "w='min(iw,ih)':"
            "h='min(iw,ih)':"
            "x='(iw-min(iw,ih))/2':"
            "y='(ih-min(iw,ih))/2',"
            "scale=1080:1080[outv]"
        )
        filter_parts.append(crop_filter)
    else:
        # 16:9 (YouTube/default): 1920x1080
        # Crop to 16:9 aspect ratio, centered
        crop_filter = (
            "[concat]crop="
            "w='min(iw,ih*16/9)':"
            "h='min(ih,iw*9/16)':"
            "x='(iw-min(iw,ih*16/9))/2':"
            "y='(ih-min(ih,iw*9/16))/2',"
            "scale=1920:1080[outv]"
        )
        filter_parts.append(crop_filter)

    filter_complex = ";".join(filter_parts)

    # Build ffmpeg command
    cmd = ["ffmpeg", "-y"]
    for src_path in source_paths:
        cmd.extend(["-i", src_path])

    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-c:v", "h264_videotoolbox",
        "-b:v", "12M",
        "-tag:v", "avc1",
        "-movflags", "+faststart",
        "-an",  # No audio for now
        output_path,
    ])

    logger.info("Stitching %d clips from %d sources → %s", n, len(source_paths), output_path)
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        logger.error("ffmpeg stitch failed: %s", result.stderr[:500])
        # Fallback: try simpler concat approach
        return _stitch_fallback(clip_entries, output_path)

    logger.info("Stitched successfully: %s", output_path)
    return output_path


def _stitch_fallback(clip_entries: list[dict], output_path: str) -> str:
    """Fallback: trim and concat without filter_complex (no speed ramps)."""
    logger.info("Using fallback stitch method (no speed ramps)")

    with tempfile.TemporaryDirectory(prefix="videopeen_stitch_") as work_dir:
        trimmed_paths = []

        for i, entry in enumerate(clip_entries):
            trimmed = os.path.join(work_dir, f"trimmed_{i:04d}.mp4")
            duration = entry["end_time"] - entry["start_time"]
            if duration <= 0:
                continue

            cmd = [
                "ffmpeg", "-y",
                "-ss", f"{entry['start_time']:.3f}",
                "-i", entry["source_path"],
                "-t", f"{duration:.3f}",
                "-c:v", "h264_videotoolbox", "-b:v", "8M", "-tag:v", "avc1",
                "-an",
                "-reset_timestamps", "1",
                trimmed,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0 and os.path.exists(trimmed):
                trimmed_paths.append(trimmed)

        if not trimmed_paths:
            raise ValueError("Fallback stitch: no clips trimmed successfully")

        # Concat
        concat_file = os.path.join(work_dir, "concat_list.txt")
        with open(concat_file, "w") as f:
            for p in trimmed_paths:
                f.write(f"file '{p}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            "-movflags", "+faststart",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Fallback concat failed: {result.stderr[:300]}")

    logger.info("Fallback stitch completed: %s", output_path)
    return output_path


# ---------------------------------------------------------------------------
# Legacy compat
# ---------------------------------------------------------------------------

def trim_clip(input_path: str, start: float, end: float, output_path: str) -> str:
    """Legacy trim."""
    duration = end - start
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-ss", f"{start:.3f}", "-t", f"{duration:.3f}",
        "-c", "copy", "-avoid_negative_ts", "make_zero",
        "-reset_timestamps", "1", output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Trim failed: {result.stderr[:300]}")
    return output_path


def stitch_clips(clip_entries: list[dict], output_path: str, temp_dir: str | None = None) -> str:
    """Legacy stitch entry point."""
    return stitch_clips_v2(
        [{"source_path": e["source_path"], "start_time": e["start_time"],
          "end_time": e["end_time"], "speed_factor": 1.0} for e in clip_entries],
        output_path,
    )
