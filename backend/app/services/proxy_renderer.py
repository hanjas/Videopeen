"""Proxy clip pre-rendering and fast concatenation for instant preview."""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Max concurrent ffmpeg processes (3 to avoid OOM on 18GB RAM)
MAX_CONCURRENT_RENDERS = 3


async def pre_render_proxy_clips(
    project_id: str,
    clips: list[dict[str, Any]],
    proxies_dir: str,
    db=None,
) -> dict[str, str]:
    """Pre-render each clip as individual 480p mp4 files (LEGO blocks).
    
    For each clip:
    - Extract the clip segment from source video
    - Encode at 480p, fast preset, crf 28
    - Apply speed factor
    - Save to: proxies_dir/{clip_id}.mp4
    
    Args:
        project_id: Project ID for logging
        clips: List of clip dicts with source_path, start_time, end_time, speed_factor, clip_id
        proxies_dir: Directory to save proxy files
        db: Optional MongoDB database connection to update clip records
    
    Returns:
        Dict mapping clip_id -> proxy_path
    """
    if not clips:
        logger.warning("No clips to pre-render for project %s", project_id)
        return {}
    
    Path(proxies_dir).mkdir(parents=True, exist_ok=True)
    
    proxy_map: dict[str, str] = {}
    
    # Use semaphore to limit concurrent renders
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_RENDERS)
    
    async def render_one_clip(clip: dict[str, Any]) -> tuple[str, str | None]:
        """Render a single proxy clip. Returns (clip_id, proxy_path or None)."""
        clip_id = clip.get("clip_id")
        if not clip_id:
            logger.warning("Clip missing clip_id: %s", clip)
            return ("", None)
        
        source_path = clip.get("source_path", "")
        start_time = clip.get("start_time", 0)
        end_time = clip.get("end_time", 0)
        speed_factor = clip.get("speed_factor", 1.0)
        
        if not source_path or not os.path.exists(source_path):
            logger.warning("Clip %s has invalid source: %s", clip_id, source_path)
            return (clip_id, None)
        
        duration = end_time - start_time
        if duration <= 0:
            logger.warning("Clip %s has invalid duration: %.2f", clip_id, duration)
            return (clip_id, None)
        
        # Encode speed_factor in filename so we can detect changes later
        if speed_factor != 1.0:
            output_path = os.path.join(proxies_dir, f"{clip_id}_s{speed_factor:.1f}.mp4")
        else:
            output_path = os.path.join(proxies_dir, f"{clip_id}.mp4")
        
        # Skip if already exists and is valid
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            logger.debug("Proxy already exists for clip %s", clip_id)
            return (clip_id, output_path)
        
        async with semaphore:
            # Build ffmpeg command
            # Use setpts to apply speed: setpts={1/speed}*PTS
            # For speed=2.0, setpts=0.5*PTS (half the PTS = 2x speed)
            # For speed=0.75, setpts=1.333*PTS (slower)
            
            if speed_factor != 1.0 and speed_factor > 0:
                vf = f"scale=-2:480,setpts={1.0/speed_factor:.6f}*PTS,format=yuv420p"
            else:
                vf = "scale=-2:480,format=yuv420p"
            
            cmd = [
                "ffmpeg", "-y",
                "-ss", f"{start_time:.3f}",
                "-i", source_path,
                "-t", f"{duration:.3f}",
                "-vf", vf,
                "-c:v", "h264_videotoolbox",
                "-b:v", "2M",
                "-tag:v", "avc1",
                "-an",  # No audio
                "-movflags", "+faststart",
                output_path,
            ]
            
            logger.debug("Rendering proxy for clip %s: %.1fs @ %.2fx speed", 
                        clip_id, duration, speed_factor)
            
            try:
                result = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await result.communicate()
                
                if result.returncode != 0:
                    logger.error("Proxy render failed for clip %s: %s", 
                               clip_id, stderr.decode()[:300])
                    return (clip_id, None)
                
                if not os.path.exists(output_path):
                    logger.error("Proxy output missing for clip %s", clip_id)
                    return (clip_id, None)
                
                logger.debug("Proxy rendered: %s (%.1f KB)", 
                           clip_id, os.path.getsize(output_path) / 1024)
                return (clip_id, output_path)
                
            except Exception as e:
                logger.exception("Exception rendering proxy for clip %s", clip_id)
                return (clip_id, None)
    
    # Render all clips in parallel (limited by semaphore)
    logger.info("Pre-rendering %d proxy clips for project %s (max %d concurrent)", 
               len(clips), project_id, MAX_CONCURRENT_RENDERS)
    
    tasks = [render_one_clip(clip) for clip in clips]
    results = await asyncio.gather(*tasks)
    
    # Build proxy map
    for clip_id, proxy_path in results:
        if proxy_path:
            proxy_map[clip_id] = proxy_path
    
    logger.info("Pre-rendered %d/%d proxy clips for project %s", 
               len(proxy_map), len(clips), project_id)
    
    # Update DB if provided
    if db is not None:
        try:
            for clip_id, proxy_path in proxy_map.items():
                # Update edit_plan timeline clips
                await db.edit_plans.update_one(
                    {"project_id": project_id, "timeline.clips.clip_id": clip_id},
                    {"$set": {"timeline.clips.$.proxy_path": proxy_path}},
                )
                # Update edit_plan clip_pool
                await db.edit_plans.update_one(
                    {"project_id": project_id, "clip_pool.clip_id": clip_id},
                    {"$set": {"clip_pool.$.proxy_path": proxy_path}},
                )
        except Exception as e:
            logger.warning("Failed to update proxy_path in DB: %s", e)
    
    return proxy_map


async def fast_concat_proxies(
    clip_ids: list[str],
    proxy_map: dict[str, str],
    output_path: str,
    project_id: str = "",
) -> str:
    """Concatenate pre-rendered proxy clips using ffmpeg concat demuxer.
    
    This is container-level stitching with no re-encoding. Takes 2-3 seconds.
    
    Args:
        clip_ids: Ordered list of clip IDs to concatenate
        proxy_map: Dict mapping clip_id -> proxy file path
        output_path: Output path for concatenated proxy
        project_id: Project ID for logging
    
    Returns:
        Path to concatenated proxy video
    
    Raises:
        ValueError: If no valid clips to concatenate
        RuntimeError: If ffmpeg concat fails
    """
    if not clip_ids:
        raise ValueError("No clips to concatenate")
    
    # Collect proxy paths in order, skip missing
    proxy_paths = []
    for clip_id in clip_ids:
        proxy_path = proxy_map.get(clip_id)
        if proxy_path and os.path.exists(proxy_path):
            proxy_paths.append(proxy_path)
        else:
            logger.warning("Missing proxy for clip %s (project %s)", clip_id, project_id)
    
    if not proxy_paths:
        raise ValueError("No valid proxy clips to concatenate")
    
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    # Write concat list file
    concat_list_path = output_path.replace(".mp4", "_concat_list.txt")
    with open(concat_list_path, "w") as f:
        for proxy_path in proxy_paths:
            # Use absolute path to avoid issues with relative paths
            abs_path = os.path.abspath(proxy_path)
            f.write(f"file '{abs_path}'\n")
    
    logger.info("Fast concat %d proxy clips → %s (project %s)", 
               len(proxy_paths), output_path, project_id)
    
    # Use concat demuxer with copy codec (no re-encoding)
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_list_path,
        "-c", "copy",
        "-movflags", "+faststart",
        output_path,
    ]
    
    try:
        result = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await result.communicate()
        
        if result.returncode != 0:
            stderr_text = stderr.decode()
            logger.error("Fast concat failed (project %s): %s", project_id, stderr_text[:500])
            raise RuntimeError(f"ffmpeg concat failed: {stderr_text[:200]}")
        
        if not os.path.exists(output_path):
            raise RuntimeError("Concat output file not created")
        
        # Clean up concat list
        try:
            os.remove(concat_list_path)
        except:
            pass
        
        size_kb = os.path.getsize(output_path) / 1024
        logger.info("Fast concat complete: %s (%.1f KB, %d clips)", 
                   output_path, size_kb, len(proxy_paths))
        
        return output_path
        
    except Exception as e:
        logger.exception("Exception during fast concat (project %s)", project_id)
        raise RuntimeError(f"Fast concat failed: {str(e)}")


async def get_existing_proxies(clips: list[dict[str, Any]], proxies_dir: str) -> dict[str, str]:
    """Check which clips already have rendered proxies.
    
    Returns dict mapping clip_id -> proxy_path for existing proxies.
    Checks both legacy {clip_id}.mp4 and speed-encoded {clip_id}_s{speed}.mp4 formats.
    """
    proxy_map: dict[str, str] = {}
    
    for clip in clips:
        clip_id = clip.get("clip_id")
        speed_factor = clip.get("speed_factor", 1.0)
        if not clip_id:
            continue
        
        # Check for speed-encoded proxy first
        if speed_factor != 1.0:
            proxy_path = os.path.join(proxies_dir, f"{clip_id}_s{speed_factor:.1f}.mp4")
            if os.path.exists(proxy_path) and os.path.getsize(proxy_path) > 1000:
                proxy_map[clip_id] = proxy_path
                continue
        
        # Check legacy proxy file (no speed suffix)
        proxy_path = os.path.join(proxies_dir, f"{clip_id}.mp4")
        if os.path.exists(proxy_path) and os.path.getsize(proxy_path) > 1000:
            proxy_map[clip_id] = proxy_path
            continue
        
        # Also check if proxy_path is stored in clip dict
        if "proxy_path" in clip and os.path.exists(clip["proxy_path"]):
            proxy_map[clip_id] = clip["proxy_path"]
    
    return proxy_map


def identify_new_clips(
    new_timeline: list[dict[str, Any]],
    existing_proxy_map: dict[str, str],
) -> list[dict[str, Any]]:
    """Identify clips that need new proxy rendering.
    
    Returns list of clips that don't have existing proxies or have changed speed_factor.
    Proxies encode speed_factor in filename: {clip_id}_s{speed}.mp4
    """
    new_clips = []
    
    for clip in new_timeline:
        clip_id = clip.get("clip_id")
        speed_factor = clip.get("speed_factor", 1.0)
        
        if not clip_id:
            continue
        
        # Check if proxy exists
        if clip_id not in existing_proxy_map:
            new_clips.append(clip)
            continue
        
        # Check if speed_factor has changed by examining proxy filename
        proxy_path = existing_proxy_map.get(clip_id, "")
        proxy_filename = os.path.basename(proxy_path)
        
        # Expected format: {clip_id}_s{speed}.mp4 or just {clip_id}.mp4 (legacy, speed=1.0)
        if f"_s{speed_factor:.1f}" not in proxy_filename and speed_factor != 1.0:
            # Speed has changed, need to re-render
            logger.debug("Clip %s speed changed to %.1fx, re-rendering proxy", clip_id, speed_factor)
            new_clips.append(clip)
        elif "_s" not in proxy_filename and speed_factor == 1.0:
            # Legacy proxy without speed suffix, but speed is 1.0, so it's still valid
            pass
        elif "_s" in proxy_filename:
            # Extract speed from filename and compare
            import re
            match = re.search(r"_s([\d.]+)\.mp4$", proxy_filename)
            if match:
                proxy_speed = float(match.group(1))
                if abs(proxy_speed - speed_factor) > 0.01:
                    logger.debug("Clip %s speed changed from %.1fx to %.1fx, re-rendering", 
                               clip_id, proxy_speed, speed_factor)
                    new_clips.append(clip)
    
    return new_clips
