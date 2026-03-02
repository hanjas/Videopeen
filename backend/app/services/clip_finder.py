"""Smart clip finding system — Layer 0 (Regex Search) + Layer 5 (Honest Admission).

Implements the first and last layers of the smart clip finding escalation system.
Layer 0: Fast regex/fuzzy text search across clip descriptions.
Layer 5: Honest admission when nothing is found.

See docs/SMART-CLIP-FINDING.md for full design context.
"""

from __future__ import annotations

import logging
import re
from typing import Any

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
# Main Orchestrator
# ---------------------------------------------------------------------------


async def smart_find_clip(
    query: str,
    all_clips: list[dict],
    project_id: str | None = None,
) -> dict[str, Any]:
    """Main entry point for smart clip finding. Escalates through layers.
    
    Current implementation: Layer 0 → Layer 5
    Future: Will add Layers 2-4 in between.
    
    Args:
        query: User's search query (e.g., "the garam masala scene")
        all_clips: List of all available clips in the project
        project_id: Optional project ID for logging/debugging
        
    Returns:
        Success: {"type": "found", "clips": [...], "layer": 0}
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
    
    # No matches found → Layer 5: Honest admission
    logger.info(f"{log_prefix} Layer 0 FAILED: no matches found, returning not_found response")
    return build_not_found_response(query)
