"""Stitch selected clips into final output video with speed ramps."""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def _detect_audio_streams(source_paths: list[str]) -> dict[str, bool]:
    """Detect which source videos have audio streams.
    
    Returns dict mapping source_path -> has_audio (bool).
    Uses ffprobe to check for audio streams.
    """
    has_audio = {}
    
    for path in source_paths:
        try:
            # Use ffprobe to detect audio stream
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=codec_type",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            
            # If output contains "audio", the file has an audio stream
            has_audio[path] = "audio" in result.stdout.lower()
            
            if not has_audio[path]:
                logger.info("Source video has no audio track: %s", os.path.basename(path))
                
        except Exception as e:
            logger.warning("Failed to detect audio for %s: %s", path, e)
            # Assume no audio on error to avoid crashes
            has_audio[path] = False
    
    return has_audio


def _build_atempo_chain(speed: float) -> str:
    """Build atempo filter chain for speed adjustments.
    
    atempo accepts 0.5-100.0, but quality degrades >2.0.
    For better quality, chain multiple atempo filters:
    - speed=4.0 → atempo=2.0,atempo=2.0
    - speed=0.25 → atempo=0.5,atempo=0.5
    
    Args:
        speed: Speed factor (1.0 = normal, 2.0 = double speed, 0.5 = half speed)
    
    Returns:
        Comma-prefixed atempo filter string (e.g., ",atempo=2.0,atempo=2.0")
    """
    if speed <= 0 or speed == 1.0:
        return ""
    
    atempo_filters = []
    remaining_speed = speed
    
    # Chain atempo filters to stay within optimal range
    while remaining_speed > 2.0:
        atempo_filters.append("atempo=2.0")
        remaining_speed /= 2.0
    
    while remaining_speed < 0.5:
        atempo_filters.append("atempo=0.5")
        remaining_speed /= 0.5
    
    # Apply the remaining speed adjustment
    if abs(remaining_speed - 1.0) > 0.01:  # Only if significantly different from 1.0
        atempo_filters.append(f"atempo={remaining_speed:.6f}")
    
    return "," + ",".join(atempo_filters) if atempo_filters else ""


def stitch_clips_v2(
    clip_entries: list[dict],
    output_path: str,
    aspect_ratio: str = "16:9",
    transition_type: str = "fade",
    transition_duration: float = 0.5,
) -> str:
    """Stitch clips with speed ramps and transitions using ffmpeg filter_complex.
    
    Each entry has:
        - source_path: path to source video
        - start_time: float seconds
        - end_time: float seconds
        - speed_factor: float (1.0 = normal, 2.0 = 2x speed, 0.75 = slow-mo)
    
    Args:
        clip_entries: List of clip dictionaries with timing and source info
        output_path: Output file path
        aspect_ratio: Target aspect ratio - "16:9" (default), "9:16" (vertical), or "1:1" (square)
        transition_type: Transition type - "none", "fade", "wiperight", "slideright", "smoothleft"
        transition_duration: Duration of transition in seconds (0.3-1.0)
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
    
    # Detect which sources have audio streams
    sources_with_audio = _detect_audio_streams(source_paths)

    filter_parts = []
    video_concat_inputs = []
    audio_concat_inputs = []

    for i, entry in enumerate(clip_entries):
        src_idx = source_index[entry["source_path"]]
        start = entry["start_time"]
        end = entry["end_time"]
        speed = entry.get("speed_factor", 1.0)
        duration = end - start

        if duration <= 0:
            continue

        # Trim video and normalize pixel format for consistent concat
        video_filter = f"[{src_idx}:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS,setsar=1,format=yuv420p"

        # Apply speed change if needed
        if speed != 1.0 and speed > 0:
            video_filter += f",setpts={1.0/speed:.4f}*PTS"

        video_filter += f"[v{i}]"
        filter_parts.append(video_filter)
        video_concat_inputs.append(f"[v{i}]")
        
        # Audio processing (only if source has audio)
        if sources_with_audio.get(entry["source_path"], False):
            audio_filter = f"[{src_idx}:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS"
            
            # Apply atempo filter for speed adjustments
            # atempo range: 0.5-100.0, but quality degrades >2.0
            # Chain multiple atempo filters for better quality
            if speed != 1.0 and speed > 0:
                audio_filter += _build_atempo_chain(speed)
            
            # Resample to 44100 Hz for consistent sample rate
            audio_filter += ",aresample=44100"
            
            audio_filter += f"[a{i}]"
            filter_parts.append(audio_filter)
            audio_concat_inputs.append(f"[a{i}]")
        else:
            # Generate silent audio for clips without audio to maintain sync
            # Use anullsrc with duration matching the video clip
            effective_duration = duration / speed if speed > 0 else duration
            audio_filter = f"anullsrc=channel_layout=stereo:sample_rate=44100,atrim=duration={effective_duration:.3f}[a{i}]"
            filter_parts.append(audio_filter)
            audio_concat_inputs.append(f"[a{i}]")

    if not video_concat_inputs:
        raise ValueError("No valid clips after filtering")

    n = len(video_concat_inputs)
    
    # ---------------------------------------------------------------------------
    # Video: xfade transitions or simple concat
    # ---------------------------------------------------------------------------
    if transition_type != "none" and n > 1:
        # Use xfade filter chain for transitions
        # Calculate effective durations for offset computation
        effective_durations = []
        for entry in clip_entries:
            duration = entry["end_time"] - entry["start_time"]
            speed = entry.get("speed_factor", 1.0)
            if duration > 0 and speed > 0:
                effective_durations.append(duration / speed)
        
        # Build xfade chain
        # First clip is the base
        current_label = f"[v0]"
        
        for i in range(1, n):
            # Calculate offset: cumulative duration of previous clips minus cumulative overlaps
            # offset = sum(durations[0:i]) - i * transition_duration
            cumulative_duration = sum(effective_durations[:i])
            offset = cumulative_duration - (i * transition_duration)
            
            # Ensure offset is non-negative
            if offset < 0:
                logger.warning("Negative xfade offset %.3f for clip %d, clamping to 0", offset, i)
                offset = 0
            
            next_label = f"[xf{i}]" if i < n - 1 else "[concat]"
            xfade_filter = f"{current_label}[v{i}]xfade=transition={transition_type}:duration={transition_duration:.3f}:offset={offset:.3f}{next_label}"
            filter_parts.append(xfade_filter)
            current_label = next_label
    else:
        # No transitions: simple concat
        video_concat_filter = "".join(video_concat_inputs) + f"concat=n={n}:v=1:a=0[concat]"
        filter_parts.append(video_concat_filter)
    
    # ---------------------------------------------------------------------------
    # Audio: acrossfade transitions or simple concat
    # ---------------------------------------------------------------------------
    if transition_type != "none" and n > 1:
        # Use acrossfade filter chain for audio transitions
        # Calculate effective durations for offset computation
        effective_durations = []
        for entry in clip_entries:
            duration = entry["end_time"] - entry["start_time"]
            speed = entry.get("speed_factor", 1.0)
            if duration > 0 and speed > 0:
                effective_durations.append(duration / speed)
        
        # Build acrossfade chain
        current_label = f"[a0]"
        
        for i in range(1, n):
            # Calculate offset: same as video
            cumulative_duration = sum(effective_durations[:i])
            offset = cumulative_duration - (i * transition_duration)
            
            if offset < 0:
                logger.warning("Negative acrossfade offset %.3f for clip %d, clamping to 0", offset, i)
                offset = 0
            
            next_label = f"[af{i}]" if i < n - 1 else "[aconcat]"
            # acrossfade parameters: d=duration, c1=tri (triangular fade curve), c2=tri
            acrossfade_filter = f"{current_label}[a{i}]acrossfade=d={transition_duration:.3f}:c1=tri:c2=tri{next_label}"
            filter_parts.append(acrossfade_filter)
            current_label = next_label
    else:
        # No transitions: simple concat
        audio_concat_filter = "".join(audio_concat_inputs) + f"concat=n={n}:v=0:a=1[aconcat]"
        filter_parts.append(audio_concat_filter)
    
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
    
    # Audio normalization (loudnorm) - streaming standard (-14 LUFS)
    audio_norm_filter = "[aconcat]loudnorm=I=-14:TP=-1:LRA=11[outa]"
    filter_parts.append(audio_norm_filter)

    filter_complex = ";".join(filter_parts)

    # Build ffmpeg command
    cmd = ["ffmpeg", "-y"]
    for src_path in source_paths:
        cmd.extend(["-i", src_path])

    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-map", "[outa]",
        "-c:v", "h264_videotoolbox",
        "-b:v", "12M",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "44100",
        "-tag:v", "avc1",
        "-movflags", "+faststart",
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
                "-c:a", "aac", "-b:a", "192k",
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
