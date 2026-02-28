"""Apply text overlays to rendered videos using ffmpeg drawtext filter."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Font paths for macOS (fallback to system default if not found)
FONT_PATHS = {
    "helvetica": "/System/Library/Fonts/Helvetica.ttc",
    "system": "/System/Library/Fonts/SFNS.ttf",  # SF Pro system font
}


def _get_font_path(prefer_bold: bool = False) -> str | None:
    """Get available font path, or None to use system default.
    
    Note: Helvetica.ttc is a TrueType Collection containing multiple weights.
    FFmpeg will use the default weight, but drawtext doesn't support selecting
    specific weights from .ttc files. For bold text, we rely on the borderw parameter.
    """
    if os.path.exists(FONT_PATHS["helvetica"]):
        return FONT_PATHS["helvetica"]
    if os.path.exists(FONT_PATHS["system"]):
        return FONT_PATHS["system"]
    # Return None to let ffmpeg use system default font
    logger.info("No font file found, using ffmpeg default font")
    return None


def _escape_drawtext(text: str) -> str:
    """Escape special characters for drawtext filter.
    
    drawtext requires:
    - Single quotes escaped as \'
    - Colon as \\:
    - Newlines as \\n (but we don't support multiline for now)
    """
    text = text.replace("'", "\\'")  # Escape single quotes
    text = text.replace(":", "\\:")  # Escape colons
    text = text.replace("%", "\\%")  # Escape percent
    return text


def _build_drawtext_filter(
    text: str,
    start_time: float,
    end_time: float,
    position: str = "bottom-center",
    style: str = "bold-white",
    font_size: int = 48,
    aspect_ratio: str = "16:9",
) -> str:
    """Build a single drawtext filter string.
    
    Args:
        text: Text to display (will be escaped)
        start_time: Start time in seconds
        end_time: End time in seconds
        position: Position - "top-left", "top-center", "bottom-center", "center"
        style: Style preset - "bold-white", "subtitle-bar", "minimal"
        font_size: Font size in pixels
        aspect_ratio: Video aspect ratio to adjust positioning
    
    Returns:
        drawtext filter string (without leading comma)
    """
    escaped_text = _escape_drawtext(text)
    
    # Adjust font size for vertical videos (narrower, need bigger text)
    if aspect_ratio == "9:16":
        font_size = int(font_size * 1.3)
    elif aspect_ratio == "1:1":
        font_size = int(font_size * 1.1)
    
    # Position expressions
    positions = {
        "top-left": "x=40:y=40",
        "top-center": "x=(w-text_w)/2:y=40",
        "bottom-center": "x=(w-text_w)/2:y=h-th-60",
        "center": "x=(w-text_w)/2:y=(h-text_h)/2",
    }
    pos_expr = positions.get(position, positions["bottom-center"])
    
    # Style presets
    font_path = _get_font_path(prefer_bold=(style == "bold-white"))
    fontfile_param = f":fontfile={font_path}" if font_path else ""
    
    if style == "bold-white":
        # White text with thick black outline
        style_params = (
            f"fontcolor=white:fontsize={font_size}"
            f":borderw=4:bordercolor=black"
            f"{fontfile_param}"
        )
    elif style == "subtitle-bar":
        # White text on semi-transparent black box (like subtitles)
        # Use box=1 with box color and opacity
        style_params = (
            f"fontcolor=white:fontsize={font_size}"
            f":box=1:boxcolor=black@0.6:boxborderw=20"
            f"{fontfile_param}"
        )
    elif style == "minimal":
        # Small white text with subtle shadow
        smaller_size = int(font_size * 0.7)
        style_params = (
            f"fontcolor=white:fontsize={smaller_size}"
            f":shadowx=2:shadowy=2:shadowcolor=black@0.5"
            f"{fontfile_param}"
        )
    else:
        # Fallback: basic white text
        style_params = f"fontcolor=white:fontsize={font_size}{fontfile_param}"
    
    # Build complete drawtext filter
    # Use enable='between(t,start,end)' for timed display
    filter_str = (
        f"drawtext=text='{escaped_text}':"
        f"{style_params}:"
        f"{pos_expr}:"
        f"enable='between(t,{start_time:.3f},{end_time:.3f})'"
    )
    
    return filter_str


def apply_text_overlays(
    input_path: str,
    output_path: str,
    overlays: list[dict],
    aspect_ratio: str = "16:9",
) -> str:
    """Apply text overlays to a video.
    
    Each overlay dict should contain:
    {
        "text": "2 cloves garlic",
        "start_time": 5.0,
        "end_time": 8.0,
        "position": "bottom-center",  # optional, default "bottom-center"
        "style": "bold-white",  # optional, default "bold-white"
        "font_size": 48  # optional, default 48
    }
    
    Args:
        input_path: Path to input video (rendered without overlays)
        output_path: Path to output video (with overlays)
        overlays: List of overlay dictionaries
        aspect_ratio: Video aspect ratio for positioning adjustments
    
    Returns:
        Path to output video
    
    Raises:
        ValueError: If overlays list is empty or invalid
        RuntimeError: If ffmpeg command fails
    """
    if not overlays:
        logger.info("No overlays to apply, copying input to output")
        # Just copy the file if no overlays
        import shutil
        shutil.copy2(input_path, output_path)
        return output_path
    
    if not os.path.exists(input_path):
        raise ValueError(f"Input video not found: {input_path}")
    
    # Ensure output directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    # Build filter chain with multiple drawtext filters
    filter_parts = []
    for overlay in overlays:
        text = overlay.get("text", "")
        if not text:
            logger.warning("Skipping overlay with empty text")
            continue
        
        start_time = overlay.get("start_time", 0.0)
        end_time = overlay.get("end_time", 0.0)
        if end_time <= start_time:
            logger.warning("Skipping overlay with invalid time range: %s", overlay)
            continue
        
        position = overlay.get("position", "bottom-center")
        style = overlay.get("style", "bold-white")
        font_size = overlay.get("font_size", 48)
        
        drawtext_filter = _build_drawtext_filter(
            text=text,
            start_time=start_time,
            end_time=end_time,
            position=position,
            style=style,
            font_size=font_size,
            aspect_ratio=aspect_ratio,
        )
        filter_parts.append(drawtext_filter)
    
    if not filter_parts:
        logger.warning("No valid overlays to apply")
        import shutil
        shutil.copy2(input_path, output_path)
        return output_path
    
    # Chain all drawtext filters with commas
    vf_filter = ",".join(filter_parts)
    
    # Build ffmpeg command
    # Apply overlays with hardware encoding for speed
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", vf_filter,
        "-c:v", "h264_videotoolbox",
        "-b:v", "12M",
        "-c:a", "copy",  # Copy audio stream unchanged
        "-tag:v", "avc1",
        "-movflags", "+faststart",
        output_path,
    ]
    
    logger.info("Applying %d text overlays to %s → %s", len(filter_parts), input_path, output_path)
    logger.debug("FFmpeg overlay command: %s", " ".join(cmd))
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode != 0:
            logger.error("FFmpeg overlay failed: %s", result.stderr[:500])
            raise RuntimeError(f"FFmpeg overlay failed: {result.stderr[:200]}")
        
        if not os.path.exists(output_path):
            raise RuntimeError("Output file was not created")
        
        logger.info("Successfully applied text overlays: %s", output_path)
        return output_path
        
    except subprocess.TimeoutExpired:
        logger.error("FFmpeg overlay timed out after 300s")
        raise RuntimeError("Text overlay rendering timed out")
    except Exception as e:
        logger.exception("Failed to apply text overlays")
        raise RuntimeError(f"Text overlay failed: {str(e)}")


def auto_generate_overlays_from_recipe(
    recipe_steps: list[str],
    clips: list[dict],
    style: str = "bold-white",
) -> list[dict]:
    """Auto-generate text overlays from recipe steps.
    
    Maps recipe steps to timeline clips by matching descriptions or order.
    
    Args:
        recipe_steps: List of recipe step strings (e.g., ["Dice onions", "Heat oil", ...])
        clips: List of clip dictionaries from timeline (must have start_time, end_time, description)
        style: Style preset to use for all overlays
    
    Returns:
        List of overlay dictionaries ready for apply_text_overlays
    """
    if not recipe_steps or not clips:
        logger.warning("No recipe steps or clips to generate overlays from")
        return []
    
    overlays = []
    
    # Sort clips by order
    sorted_clips = sorted(clips, key=lambda c: c.get("order", 0))
    
    # Simple strategy: match recipe steps to clips by order
    # More sophisticated: use LLM to match step descriptions to clip descriptions
    
    for i, step in enumerate(recipe_steps):
        if i >= len(sorted_clips):
            logger.warning("More recipe steps than clips, stopping at step %d", i)
            break
        
        clip = sorted_clips[i]
        
        # Show overlay at the beginning of each clip
        start_time = clip.get("start_time", 0.0)
        end_time = clip.get("end_time", 0.0)
        
        # Display for first 3-5 seconds of the clip (or whole clip if shorter)
        clip_duration = end_time - start_time
        display_duration = min(clip_duration, 4.0)  # Show for 4 seconds max
        
        overlay = {
            "text": f"Step {i+1}: {step}",
            "start_time": start_time,
            "end_time": start_time + display_duration,
            "position": "bottom-center",
            "style": style,
            "font_size": 48,
        }
        
        overlays.append(overlay)
        logger.debug("Generated overlay for step %d: %s at %.1f-%.1fs",
                     i+1, step, overlay["start_time"], overlay["end_time"])
    
    logger.info("Auto-generated %d overlays from recipe steps", len(overlays))
    return overlays
