"""Smart clip finding system — Layer 0, 2, 3, and 5.

Implements the smart clip finding escalation system:
Layer 0: Fast regex/fuzzy text search across clip descriptions.
Layer 2: Visual re-check of candidate clips using Claude vision.
Layer 3: Targeted re-scan (gap scanning + generic clip re-scanning).
Layer 5: Honest admission when nothing is found.

See docs/SMART-CLIP-FINDING.md for full design context.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from app.config import settings
from app.services.video_analyzer import (
    _build_async_client,
    _encode_image,
    _resolve_api_key,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Layer 0: Regex/Fuzzy Text Search
# ---------------------------------------------------------------------------


def _normalize_text(text: str) -> str:
    """Normalize text for matching: lowercase, strip punctuation."""
    return re.sub(r'[^\w\s]', '', text.lower()).strip()


def _extract_keywords(query: str) -> list[str]:
    """Extract keywords from query: words > 2 chars, lowercased."""
    normalized = _normalize_text(query)
    words = normalized.split()
    # Filter words longer than 2 characters
    keywords = [w for w in words if len(w) > 2]
    return keywords


def _count_keyword_matches(text: str, keywords: list[str]) -> int:
    """Count how many keywords match in the given text (case-insensitive)."""
    normalized = _normalize_text(text)
    score = 0
    for keyword in keywords:
        if keyword in normalized:
            score += 1
    return score


async def find_clips_by_text(query: str, all_clips: list[dict]) -> list[dict]:
    """Layer 0: Fast regex/fuzzy text search across clip descriptions.
    
    Args:
        query: User's search query (e.g., "garam masala scene")
        all_clips: List of clip dictionaries with at least a 'description' field
        
    Returns:
        Clips sorted by relevance (number of keyword matches), descending.
        Returns empty list if nothing matches.
        Each returned clip includes a '_search_score' key with the match count.
    """
    if not query or not all_clips:
        logger.debug("find_clips_by_text: empty query or clip list")
        return []
    
    keywords = _extract_keywords(query)
    if not keywords:
        logger.debug("find_clips_by_text: no valid keywords extracted from query")
        return []
    
    logger.info(f"find_clips_by_text: searching for keywords: {keywords}")
    
    # Score each clip
    scored_clips = []
    for clip in all_clips:
        description = clip.get("description", "")
        if not description:
            continue
        
        score = _count_keyword_matches(description, keywords)
        if score > 0:
            # Make a copy so we don't mutate the original
            clip_copy = clip.copy()
            clip_copy["_search_score"] = score
            scored_clips.append(clip_copy)
    
    # Sort by score descending
    scored_clips.sort(key=lambda c: c.get("_search_score", 0), reverse=True)
    
    logger.info(f"find_clips_by_text: found {len(scored_clips)} matching clips")
    return scored_clips


# ---------------------------------------------------------------------------
# Layer 2: Visual Re-Check
# ---------------------------------------------------------------------------


async def _extract_clip_frames(
    video_path: str, start_time: float, end_time: float, num_frames: int = 3
) -> list[str]:
    """Extract frames from a clip's time range, return list of temp file paths.
    
    Args:
        video_path: Path to the source video file
        start_time: Start time in seconds
        end_time: End time in seconds
        num_frames: Number of frames to extract (default 3: start, middle, end)
        
    Returns:
        List of paths to extracted frame files (temp files that caller must clean up)
    """
    duration = max(0.1, end_time - start_time)
    
    # Calculate timestamps for evenly distributed frames
    if num_frames == 1:
        timestamps = [start_time + duration / 2]
    else:
        timestamps = [start_time + (duration * i / (num_frames - 1)) for i in range(num_frames)]
    
    frame_paths = []
    temp_dir = tempfile.mkdtemp(prefix="clip_frames_")
    
    try:
        for i, timestamp in enumerate(timestamps):
            output_path = os.path.join(temp_dir, f"frame_{i:03d}.jpg")
            
            # Use ffmpeg to extract frame at specific timestamp
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-ss", str(timestamp),
                "-i", video_path,
                "-frames:v", "1",
                "-q:v", "2",  # High quality
                "-y",  # Overwrite
                output_path,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            
            await proc.wait()
            
            if proc.returncode == 0 and os.path.exists(output_path):
                frame_paths.append(output_path)
            else:
                logger.warning(f"Failed to extract frame at {timestamp:.1f}s from {video_path}")
        
        return frame_paths
    
    except Exception as e:
        logger.error(f"Error extracting frames from {video_path}: {e}")
        # Clean up any partial files
        for path in frame_paths:
            try:
                os.remove(path)
            except Exception:
                pass
        return []


async def visual_recheck_clips(
    query: str,
    candidate_clips: list[dict],
    project_id: str,
    max_candidates: int = 8,
) -> list[dict]:
    """Layer 2: Extract frames from candidate clips and verify visually.
    
    For each candidate:
    1. Extract 3 frames (start, middle, end) from the clip's time range
    2. Send to Claude vision with a focused prompt
    3. Return clips where vision confirms the match
    
    Args:
        query: User's search query
        candidate_clips: List of candidate clips to visually verify
        project_id: Project ID to locate video files
        max_candidates: Maximum number of candidates to check (default 8)
        
    Returns:
        List of clips that passed visual verification, with _visual_score added
    """
    if not candidate_clips:
        logger.debug("visual_recheck_clips: no candidates to check")
        return []
    
    # Limit candidates
    candidates = candidate_clips[:max_candidates]
    logger.info(f"visual_recheck_clips: checking {len(candidates)} candidates for query '{query}'")
    
    # Extract frames from all candidates
    all_frames = []
    clip_frame_map = []  # Track which frames belong to which clip
    temp_files = []
    
    try:
        for clip_idx, clip in enumerate(candidates):
            # Construct video path
            source_video = clip.get("source_video", "")
            if not source_video:
                logger.warning(f"Clip {clip_idx} missing source_video field")
                continue
            
            video_path = os.path.join(settings.upload_dir, project_id, source_video)
            
            if not os.path.exists(video_path):
                logger.warning(f"Video not found: {video_path}")
                continue
            
            start_time = clip.get("start_time", 0)
            end_time = clip.get("end_time", 0)
            
            # Extract 3 frames
            frame_paths = await _extract_clip_frames(video_path, start_time, end_time, num_frames=3)
            
            if frame_paths:
                clip_frame_map.append({
                    "clip_index": clip_idx,
                    "clip": clip,
                    "frame_paths": frame_paths,
                })
                all_frames.extend(frame_paths)
                temp_files.extend(frame_paths)
        
        if not clip_frame_map:
            logger.warning("visual_recheck_clips: no frames extracted from any candidate")
            return []
        
        # Build content for Claude vision API
        content = []
        
        # Add frames grouped by clip
        for item in clip_frame_map:
            clip_idx = item["clip_index"]
            clip = item["clip"]
            frame_paths = item["frame_paths"]
            
            content.append({
                "type": "text",
                "text": f"\n--- Clip {clip_idx} ---\nDescription: {clip.get('description', 'N/A')}\nFrames (start, middle, end):"
            })
            
            for frame_path in frame_paths:
                try:
                    content.append(_encode_image(frame_path))
                except Exception as e:
                    logger.warning(f"Failed to encode frame {frame_path}: {e}")
        
        # Add the verification prompt
        prompt = f"""I'm searching for: "{query}" in a cooking video.

Above are frames from {len(clip_frame_map)} candidate clips. For each clip, I've shown 3 frames (start, middle, end) along with the clip's text description.

For each clip, tell me if it visually matches what I'm searching for. Consider:
- Does the visual content match the query?
- Does it show the action/moment being searched for?
- How confident are you in the match?

Respond ONLY with valid JSON (no markdown, no explanation):
[
  {{"clip_index": 0, "matches": true, "confidence": 0.85, "reason": "Shows garam masala being added to the pan"}},
  {{"clip_index": 1, "matches": false, "confidence": 0.2, "reason": "Shows generic stirring, no specific spice visible"}}
]"""
        
        content.append({"type": "text", "text": prompt})
        
        # Call Claude vision API
        api_key = await _resolve_api_key()
        client = _build_async_client(api_key)
        
        try:
            response = await asyncio.wait_for(
                client.messages.create(
                    model="claude-haiku-3-5-20250219",  # Fast and cheap for verification
                    max_tokens=1500,
                    messages=[{"role": "user", "content": content}],
                ),
                timeout=30.0,
            )
            
            result_text = response.content[0].text
            logger.info(f"Visual recheck API response: {len(result_text)} chars")
            
            # Parse JSON response
            try:
                # Clean markdown code fences if present
                cleaned = result_text.strip()
                if cleaned.startswith("```"):
                    cleaned = re.sub(r"```(?:json)?\s*", "", cleaned).strip()
                
                results = json.loads(cleaned)
                
                # Filter matches
                matched_clips = []
                for result in results:
                    clip_idx = result.get("clip_index")
                    matches = result.get("matches", False)
                    confidence = result.get("confidence", 0.0)
                    reason = result.get("reason", "")
                    
                    if matches and confidence > 0.6:
                        # Find the original clip
                        clip_data = None
                        for item in clip_frame_map:
                            if item["clip_index"] == clip_idx:
                                clip_data = item["clip"].copy()
                                break
                        
                        if clip_data:
                            clip_data["_visual_score"] = confidence
                            clip_data["_visual_reason"] = reason
                            matched_clips.append(clip_data)
                            logger.info(f"Clip {clip_idx} MATCHED (confidence={confidence:.2f}): {reason}")
                
                logger.info(f"visual_recheck_clips: {len(matched_clips)} clips passed visual verification")
                return matched_clips
            
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse vision API JSON response: {e}\nResponse: {result_text[:500]}")
                return []
        
        except asyncio.TimeoutError:
            logger.warning("visual_recheck_clips: API call timed out after 30s")
            return []
        
        except Exception as e:
            logger.error(f"visual_recheck_clips: API call failed: {e}")
            return []
    
    finally:
        # Clean up temp files
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception as e:
                logger.warning(f"Failed to clean up temp file {temp_file}: {e}")
        
        # Clean up temp directories
        for item in clip_frame_map:
            for frame_path in item.get("frame_paths", []):
                try:
                    temp_dir = os.path.dirname(frame_path)
                    if os.path.exists(temp_dir) and temp_dir.startswith(tempfile.gettempdir()):
                        os.rmdir(temp_dir)
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# Layer 5: Honest Admission
# ---------------------------------------------------------------------------


def build_not_found_response(query: str) -> dict[str, Any]:
    """Layer 5: Build a helpful 'not found' response with suggestions.
    
    Args:
        query: The user's original search query
        
    Returns:
        Dictionary with:
            - type: "not_found"
            - summary: A helpful message
            - suggestions: List of suggestion strings
    """
    summary = (
        f"I've searched through the entire video thoroughly and couldn't find a scene "
        f"matching '{query}'. It's possible this moment wasn't captured in the "
        f"footage, or it looks very different from what I'm searching for."
    )
    
    suggestions = [
        "Browse the clip timeline manually to find it",
        "Describe the scene differently (what was happening around it?)",
        "Upload the specific timestamp if you know it",
    ]
    
    logger.info(f"build_not_found_response: generated response for query: {query}")
    
    return {
        "type": "not_found",
        "summary": summary,
        "suggestions": suggestions,
    }


# ---------------------------------------------------------------------------
# Layer 3: Targeted Re-Scan (Gap Scanning + Generic Clip Re-Scanning)
# ---------------------------------------------------------------------------

GENERIC_KEYWORDS = [
    "stirring", "cooking", "preparing", "handling", "mixing",
    "working", "moving", "adjusting", "holding", "standing",
    "general", "overhead", "wide shot", "kitchen", "idle",
    "transition", "setup", "waiting", "pausing",
]


async def _get_video_duration(video_path: str) -> float:
    """Get video duration in seconds using ffprobe.
    
    Args:
        video_path: Path to video file
        
    Returns:
        Duration in seconds, or 0.0 if unable to determine
    """
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except Exception as e:
        logger.warning(f"Failed to get duration for {video_path}: {e}")
    return 0.0


def _create_discovered_clip(
    source_video: str,
    start_time: float,
    end_time: float,
    description: str,
    visual_quality: int = 5,
) -> dict:
    """Create a new clip dict for a discovered moment.
    
    Args:
        source_video: Source video filename
        start_time: Clip start time in seconds
        end_time: Clip end time in seconds
        description: What this clip shows
        visual_quality: Quality rating 1-10
        
    Returns:
        Clip dictionary marked with "discovered": True
    """
    return {
        "clip_id": str(uuid.uuid4()),
        "source_video": source_video,
        "start_time": start_time,
        "end_time": end_time,
        "description": description,
        "visual_quality": visual_quality,
        "discovered": True,  # Mark as discovered by Layer 3
        "action_type": "discovered",
    }


async def _extract_frames_from_range(
    video_path: str,
    start_time: float,
    end_time: float,
    num_frames: int = 5,
) -> list[tuple[float, str]]:
    """Extract frames from a specific time range in a video.
    
    Args:
        video_path: Path to video file
        start_time: Start time in seconds
        end_time: End time in seconds
        num_frames: Number of frames to extract
        
    Returns:
        List of (timestamp, frame_path) tuples
    """
    from app.config import settings
    
    frames = []
    duration = end_time - start_time
    if duration <= 0:
        return frames
    
    # Create temp directory for frames
    temp_dir = Path(settings.output_dir) / "temp_frames" / str(uuid.uuid4())
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        for i in range(num_frames):
            timestamp = start_time + (i * duration / (num_frames - 1)) if num_frames > 1 else start_time
            output_path = temp_dir / f"frame_{i:03d}.jpg"
            
            # Extract frame using ffmpeg
            cmd = [
                "ffmpeg",
                "-ss", str(timestamp),
                "-i", video_path,
                "-frames:v", "1",
                "-q:v", "2",
                "-y",
                str(output_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=10)
            if result.returncode == 0 and output_path.exists():
                frames.append((timestamp, str(output_path)))
        
    except Exception as e:
        logger.warning(f"Failed to extract frames from {video_path} [{start_time}-{end_time}]: {e}")
    
    return frames


async def _vision_scan_frames(
    query: str,
    frames: list[tuple[float, str]],
    source_video: str,
    context: str = "gap",
) -> dict | None:
    """Send frames to vision model to check if query content is present.
    
    Args:
        query: User's search query
        frames: List of (timestamp, frame_path) tuples
        source_video: Source video name for logging
        context: "gap" or "generic_clip" for logging
        
    Returns:
        {"found": True, "start": float, "end": float, "description": str} if found,
        None if not found
    """
    if not frames:
        return None
    
    from app.services.video_analyzer import _resolve_api_key, _build_async_client, _encode_image
    
    try:
        api_key = await _resolve_api_key()
        client = _build_async_client(api_key)
        
        # Build content with frames
        content: list[dict] = []
        timestamps = []
        
        for ts, frame_path in frames:
            content.append({"type": "text", "text": f"Frame at {ts:.1f}s:"})
            content.append(_encode_image(frame_path))
            timestamps.append(ts)
        
        # Focused query prompt
        prompt = f"""Analyze these {len(frames)} frames from a cooking video.

SEARCH QUERY: "{query}"

Does this sequence contain the specific moment described in the query?

Look for:
- The exact ingredient, action, or moment mentioned
- Visual confirmation (not just similar context)
- Clear visibility of what's being searched for

If found:
- Identify which frames show it
- Describe what you see specifically
- Estimate the time range where it appears

Return JSON:
{{
  "found": true/false,
  "confidence": <1-10>,
  "description": "<specific description of what you found, or why not found>",
  "start_time": <float or null>,
  "end_time": <float or null>
}}"""
        
        content.append({"type": "text", "text": prompt})
        
        # Use claude-haiku-3-5 for fast, cost-effective vision
        response = await client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=500,
            messages=[{"role": "user", "content": content}],
            timeout=30.0,
        )
        
        text = response.content[0].text
        logger.debug(f"Vision scan ({context}) response: {text[:200]}")
        
        # Parse JSON response
        import re
        cleaned = re.sub(r'```json\s*', '', text)
        cleaned = re.sub(r'```\s*', '', cleaned).strip()
        
        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError:
            # Try to extract JSON object
            start = cleaned.find('{')
            if start != -1:
                depth = 0
                for i in range(start, len(cleaned)):
                    if cleaned[i] == '{': depth += 1
                    elif cleaned[i] == '}':
                        depth -= 1
                        if depth == 0:
                            result = json.loads(cleaned[start:i+1])
                            break
            else:
                logger.warning(f"Failed to parse vision response: {text[:200]}")
                return None
        
        if result.get("found") and result.get("confidence", 0) >= 6:
            return {
                "found": True,
                "start": result.get("start_time") or timestamps[0],
                "end": result.get("end_time") or timestamps[-1],
                "description": result.get("description", query),
            }
        
    except Exception as e:
        logger.warning(f"Vision scan failed for {source_video} ({context}): {e}")
    
    return None


async def scan_gaps(
    query: str,
    all_clips: list[dict],
    project_id: str,
    min_gap_seconds: float = 1.0,
) -> list[dict]:
    """Layer 3A: Find and scan gaps between detected clips.
    
    Identifies time ranges where no clip was detected and scans them
    for the query content.
    
    Args:
        query: User's search query
        all_clips: All existing clips
        project_id: Project ID to locate video files
        min_gap_seconds: Minimum gap size to consider (default 1.0s)
        
    Returns:
        List of newly discovered clips found in gaps
    """
    from app.config import settings
    
    logger.info(f"Layer 3A: Scanning gaps (min {min_gap_seconds}s) for query: '{query}'")
    
    discovered_clips = []
    
    # Group clips by source video
    clips_by_video: dict[str, list[dict]] = {}
    for clip in all_clips:
        source = clip.get("source_video", "")
        if not source:
            continue
        if source not in clips_by_video:
            clips_by_video[source] = []
        clips_by_video[source].append(clip)
    
    # Process each video
    for source_video, clips in clips_by_video.items():
        # Find video file path
        video_path = Path(settings.upload_dir) / project_id / source_video
        if not video_path.exists():
            logger.debug(f"Video not found: {video_path}, skipping gap scan")
            continue
        
        # Get video duration
        video_duration = await _get_video_duration(str(video_path))
        if video_duration <= 0:
            logger.debug(f"Could not determine duration for {source_video}, skipping")
            continue
        
        # Sort clips by start time
        sorted_clips = sorted(clips, key=lambda c: c.get("start_time", 0))
        
        # Find gaps
        gaps = []
        
        # Gap before first clip
        if sorted_clips and sorted_clips[0].get("start_time", 0) > min_gap_seconds:
            gaps.append((0.0, sorted_clips[0]["start_time"]))
        
        # Gaps between clips
        for i in range(len(sorted_clips) - 1):
            current_end = sorted_clips[i].get("end_time", 0)
            next_start = sorted_clips[i + 1].get("start_time", 0)
            gap_size = next_start - current_end
            
            if gap_size >= min_gap_seconds:
                gaps.append((current_end, next_start))
        
        # Gap after last clip
        if sorted_clips:
            last_end = sorted_clips[-1].get("end_time", 0)
            if video_duration - last_end >= min_gap_seconds:
                gaps.append((last_end, video_duration))
        
        logger.info(f"Found {len(gaps)} gaps in {source_video} (duration: {video_duration:.1f}s)")
        
        # Scan each gap (limit to largest gaps if too many)
        if len(gaps) > 10:
            # Sort by gap size descending and take top 10
            gaps = sorted(gaps, key=lambda g: g[1] - g[0], reverse=True)[:10]
            logger.info(f"Limited to 10 largest gaps for scanning")
        
        for gap_start, gap_end in gaps:
            gap_size = gap_end - gap_start
            logger.debug(f"Scanning gap: {gap_start:.1f}s - {gap_end:.1f}s ({gap_size:.1f}s)")
            
            # Extract frames from gap (5 frames for good coverage)
            frames = await _extract_frames_from_range(
                str(video_path), gap_start, gap_end, num_frames=5
            )
            
            if not frames:
                continue
            
            # Send to vision model
            result = await _vision_scan_frames(
                query, frames, source_video, context="gap"
            )
            
            # Clean up temp frames
            for _, frame_path in frames:
                try:
                    os.remove(frame_path)
                except:
                    pass
            
            if result and result.get("found"):
                logger.info(f"✓ Found content in gap: {gap_start:.1f}-{gap_end:.1f}s")
                discovered_clip = _create_discovered_clip(
                    source_video=source_video,
                    start_time=result["start"],
                    end_time=result["end"],
                    description=result["description"],
                    visual_quality=7,  # Assume decent quality if found
                )
                discovered_clips.append(discovered_clip)
    
    logger.info(f"Layer 3A: Discovered {len(discovered_clips)} clips in gaps")
    return discovered_clips


async def scan_generic_clips(
    query: str,
    all_clips: list[dict],
    project_id: str,
    max_clips: int = 10,
) -> list[dict]:
    """Layer 3B: Re-scan clips with generic descriptions using focused vision.
    
    Identifies clips with vague descriptions and re-examines them with
    the specific query in mind.
    
    Args:
        query: User's search query
        all_clips: All existing clips
        project_id: Project ID to locate video files
        max_clips: Maximum number of generic clips to re-scan
        
    Returns:
        List of clips where the query content was found
    """
    from app.config import settings
    
    logger.info(f"Layer 3B: Re-scanning generic clips for query: '{query}'")
    
    # Filter clips with generic descriptions
    generic_clips = []
    for clip in all_clips:
        description = clip.get("description", "").lower()
        if any(keyword in description for keyword in GENERIC_KEYWORDS):
            generic_clips.append(clip)
    
    logger.info(f"Found {len(generic_clips)} clips with generic descriptions")
    
    if not generic_clips:
        return []
    
    # Sort by visual quality (lower quality = more likely to be mislabeled)
    # and limit to max_clips
    generic_clips.sort(key=lambda c: c.get("visual_quality", 5))
    generic_clips = generic_clips[:max_clips]
    
    matching_clips = []
    
    for clip in generic_clips:
        source_video = clip.get("source_video", "")
        start_time = clip.get("start_time", 0)
        end_time = clip.get("end_time", 0)
        
        if not source_video:
            continue
        
        # Find video file
        video_path = Path(settings.upload_dir) / project_id / source_video
        if not video_path.exists():
            logger.debug(f"Video not found: {video_path}, skipping")
            continue
        
        logger.debug(f"Re-scanning generic clip: {start_time:.1f}-{end_time:.1f}s in {source_video}")
        
        # Extract 5 frames for better coverage
        frames = await _extract_frames_from_range(
            str(video_path), start_time, end_time, num_frames=5
        )
        
        if not frames:
            continue
        
        # Send to vision model with focused query
        result = await _vision_scan_frames(
            query, frames, source_video, context="generic_clip"
        )
        
        # Clean up temp frames
        for _, frame_path in frames:
            try:
                os.remove(frame_path)
            except:
                pass
        
        if result and result.get("found"):
            logger.info(f"✓ Found specific content in generic clip: {clip.get('description', '')}")
            # Return the original clip with updated info
            enhanced_clip = clip.copy()
            enhanced_clip["_rescan_match"] = True
            enhanced_clip["_rescan_description"] = result["description"]
            matching_clips.append(enhanced_clip)
    
    logger.info(f"Layer 3B: Found {len(matching_clips)} matches in generic clips")
    return matching_clips


async def targeted_rescan(
    query: str,
    all_clips: list[dict],
    project_id: str,
) -> list[dict]:
    """Layer 3: Combined gap scan + generic clip re-scan.
    
    Runs both 3A (gap scanning) and 3B (generic clip re-scan) concurrently
    and merges the results.
    
    Args:
        query: User's search query
        all_clips: All existing clips
        project_id: Project ID to locate video files
        
    Returns:
        Combined list of discovered/enhanced clips
    """
    logger.info("Layer 3: Starting targeted re-scan (gap scan + generic re-scan)")
    
    try:
        # Run both scans concurrently with 60s timeout
        gap_task = scan_gaps(query, all_clips, project_id)
        generic_task = scan_generic_clips(query, all_clips, project_id)
        
        gap_results, generic_results = await asyncio.wait_for(
            asyncio.gather(gap_task, generic_task),
            timeout=60.0
        )
        
        # Merge results
        all_results = gap_results + generic_results
        logger.info(f"Layer 3 complete: {len(gap_results)} from gaps, {len(generic_results)} from generic clips")
        
        return all_results
        
    except asyncio.TimeoutError:
        logger.warning("Layer 3 timed out after 60s")
        return []
    except Exception as e:
        logger.error(f"Layer 3 failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Main Orchestrator
# ---------------------------------------------------------------------------


async def smart_find_clip(
    query: str,
    all_clips: list[dict],
    project_id: str | None = None,
) -> dict[str, Any]:
    """Main entry point for smart clip finding. Escalates through layers.
    
    Current implementation: Layer 0 → Layer 2 → Layer 3 → Layer 5
    - Layer 0: Fast regex/keyword text search
    - Layer 2: Visual re-check with Claude vision (NEW in task 015)
    - Layer 3: Gap scanning + generic clip re-scan
    - Layer 5: Honest admission when nothing found
    
    Args:
        query: User's search query (e.g., "the garam masala scene")
        all_clips: List of all available clips in the project
        project_id: Project ID for locating video files (required for Layers 2-3)
        
    Returns:
        Success: {"type": "found", "clips": [...], "layer": 0|2|3}
        Failure: {"type": "not_found", "summary": "...", "suggestions": [...]}
    """
    log_prefix = f"[Project {project_id}]" if project_id else ""
    logger.info(f"{log_prefix} smart_find_clip: query='{query}', total_clips={len(all_clips)}")
    
    # Layer 0: Regex/fuzzy text search
    logger.debug(f"{log_prefix} Attempting Layer 0: regex text search")
    matches = await find_clips_by_text(query, all_clips)
    
    if matches:
        logger.info(f"{log_prefix} Layer 0 SUCCESS: found {len(matches)} matches")
        return {
            "type": "found",
            "clips": matches,
            "layer": 0,
        }
    
    # Layer 2: Visual re-check
    logger.info(f"{log_prefix} Layer 0 FAILED: attempting Layer 2 (visual re-check)")
    
    if project_id and all_clips:
        # Sort all clips by partial keyword match as candidates for visual check
        keywords = _extract_keywords(query)
        if keywords:
            # Score all clips by partial keyword matches
            scored_candidates = []
            for clip in all_clips:
                description = clip.get("description", "")
                score = _count_keyword_matches(description, keywords)
                # Even clips with score=0 can be candidates (visual might match)
                clip_copy = clip.copy()
                clip_copy["_candidate_score"] = score
                scored_candidates.append(clip_copy)
            
            # Sort by score descending (highest partial match first)
            scored_candidates.sort(key=lambda c: c.get("_candidate_score", 0), reverse=True)
            
            visual_matches = await visual_recheck_clips(
                query=query,
                candidate_clips=scored_candidates,
                project_id=project_id,
                max_candidates=8,
            )
            
            if visual_matches:
                logger.info(f"{log_prefix} Layer 2 SUCCESS: found {len(visual_matches)} visual matches")
                return {
                    "type": "found",
                    "clips": visual_matches,
                    "layer": 2,
                }
        
        logger.info(f"{log_prefix} Layer 2 FAILED: no visual matches found")
    else:
        logger.debug(f"{log_prefix} Layer 2 SKIPPED: missing project_id or clips")
    
    # Layer 3: Targeted re-scan (gap scanning + generic clip re-scan)
    if project_id:
        logger.debug(f"{log_prefix} Attempting Layer 3: targeted re-scan")
        discovered = await targeted_rescan(query, all_clips, project_id)
        
        if discovered:
            logger.info(f"{log_prefix} Layer 3 SUCCESS: found {len(discovered)} clips")
            return {
                "type": "found",
                "clips": discovered,
                "layer": 3,
            }
    else:
        logger.debug(f"{log_prefix} Skipping Layer 3: no project_id provided")
    
    # No matches found → Layer 5: Honest admission
    logger.info(f"{log_prefix} All layers exhausted, returning not_found response")
    return build_not_found_response(query)
