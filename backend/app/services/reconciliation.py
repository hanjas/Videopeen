"""Reconciliation phase: Compare detected actions against recipe ingredients.

This is a pure text-matching service — NO LLM calls.
Identifies missing ingredients and suspicious gaps in the action timeline.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# Common cooking ingredients for pattern matching
COMMON_INGREDIENTS = {
    # Spices
    "turmeric", "cumin", "coriander", "chili", "chilli", "pepper", "salt",
    "garam masala", "paprika", "cardamom", "cinnamon", "cloves", "nutmeg",
    "kashmiri", "cayenne", "fennel", "mustard", "fenugreek",
    
    # Aromatics
    "onion", "garlic", "ginger", "shallot", "scallion", "leek",
    
    # Herbs
    "cilantro", "coriander leaves", "mint", "basil", "parsley", "thyme",
    "rosemary", "oregano", "bay leaf", "curry leaves",
    
    # Liquids
    "oil", "ghee", "butter", "water", "stock", "broth", "coconut milk",
    "cream", "yogurt", "milk", "vinegar", "lemon", "lime",
    
    # Proteins
    "chicken", "beef", "pork", "lamb", "fish", "shrimp", "prawn", "egg",
    "tofu", "paneer",
    
    # Vegetables
    "tomato", "potato", "carrot", "peas", "beans", "spinach", "cauliflower",
    "broccoli", "bell pepper", "capsicum", "eggplant", "zucchini",
    
    # Basics
    "flour", "rice", "pasta", "noodles", "bread", "cheese", "sugar",
    "honey", "soy sauce", "sauce", "paste",
}


def extract_ingredients_from_recipe(recipe_context: dict) -> list[str]:
    """Parse recipe steps to extract ingredient names.
    
    Uses simple keyword matching against common ingredients.
    
    Args:
        recipe_context: Dict with dish_name and recipe_steps
        
    Returns:
        List of ingredient names found in the recipe
    """
    steps = recipe_context.get("recipe_steps", [])
    if not steps:
        return []
    
    # Combine all steps into one text block
    full_text = " ".join(steps).lower()
    
    # Find all common ingredients mentioned
    found_ingredients = []
    for ingredient in COMMON_INGREDIENTS:
        # Use word boundary matching to avoid partial matches
        pattern = r'\b' + re.escape(ingredient) + r'\b'
        if re.search(pattern, full_text, re.IGNORECASE):
            found_ingredients.append(ingredient)
    
    logger.info("Extracted %d ingredients from recipe: %s",
                len(found_ingredients), found_ingredients[:10])
    return found_ingredients


def match_ingredients_to_actions(
    ingredients: list[str],
    actions: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Match recipe ingredients to detected actions using fuzzy keyword search.
    
    Args:
        ingredients: List of ingredient names from recipe
        actions: List of detected action dicts
        
    Returns:
        Tuple of (matched, unmatched) ingredient lists
        matched: [{"ingredient": "turmeric", "action_id": 5, "confidence": "high"}]
        unmatched: [{"ingredient": "garam masala"}]
    """
    matched = []
    unmatched = []
    
    for ingredient in ingredients:
        best_match = None
        best_score = 0
        
        # Search all action descriptions for this ingredient
        for action in actions:
            desc = action.get("description", "").lower()
            action_type = action.get("action_type", "")
            
            # Skip idle/setup actions
            if action_type in ["idle", "setup", "transition"]:
                continue
            
            # Check for exact match
            pattern = r'\b' + re.escape(ingredient) + r'\b'
            if re.search(pattern, desc, re.IGNORECASE):
                # Higher score for ingredient_add actions
                score = 3 if action_type == "ingredient_add" else 2
                
                # Bonus for "shows_action_moment" (hand adding vs already added)
                if action.get("shows_action_moment"):
                    score += 1
                
                if score > best_score:
                    best_score = score
                    best_match = action
        
        if best_match:
            confidence = "high" if best_score >= 3 else "medium"
            matched.append({
                "ingredient": ingredient,
                "action_id": best_match["action_id"],
                "description": best_match.get("description", ""),
                "confidence": confidence,
                "score": best_score,
            })
        else:
            unmatched.append({"ingredient": ingredient})
    
    logger.info("Matched %d/%d ingredients to actions",
                len(matched), len(ingredients))
    return matched, unmatched


def find_suspicious_gaps(
    actions: list[dict],
    min_gap_seconds: float = 10.0,
) -> list[dict]:
    """Find suspiciously long idle gaps between actions.
    
    A 40-second gap during a rapid spice-adding sequence is suspicious.
    
    Args:
        actions: List of detected actions
        min_gap_seconds: Minimum gap duration to flag
        
    Returns:
        List of suspicious gap dicts with start, end, duration, context
    """
    if not actions:
        return []
    
    # Sort actions by video and start_time
    sorted_actions = sorted(actions, key=lambda a: (
        a.get("source_video", ""),
        a.get("start_time", 0),
    ))
    
    gaps = []
    
    for i in range(len(sorted_actions) - 1):
        curr = sorted_actions[i]
        next_action = sorted_actions[i + 1]
        
        # Only check gaps within the same video
        if curr.get("source_video") != next_action.get("source_video"):
            continue
        
        curr_end = curr.get("end_time", 0)
        next_start = next_action.get("start_time", 0)
        gap_duration = next_start - curr_end
        
        if gap_duration >= min_gap_seconds:
            # Extra suspicious if surrounding actions are brief (ingredient additions)
            curr_dur = curr.get("end_time", 0) - curr.get("start_time", 0)
            next_dur = next_action.get("end_time", 0) - next_action.get("start_time", 0)
            avg_neighbor_dur = (curr_dur + next_dur) / 2
            
            # Flag if gap is much longer than neighboring actions
            suspicion = "high" if gap_duration > avg_neighbor_dur * 5 else "medium"
            
            gaps.append({
                "start": curr_end,
                "end": next_start,
                "duration": round(gap_duration, 1),
                "video": curr.get("source_video", ""),
                "context": f"between '{curr.get('description', '?')[:50]}' and '{next_action.get('description', '?')[:50]}'",
                "suspicion": suspicion,
                "prev_action_id": curr["action_id"],
                "next_action_id": next_action["action_id"],
            })
    
    # Sort by duration (longest first)
    gaps.sort(key=lambda g: g["duration"], reverse=True)
    
    if gaps:
        logger.info("Found %d suspicious gaps (>%.1fs)", len(gaps), min_gap_seconds)
    
    return gaps


def suggest_missing_ingredient_location(
    ingredient: str,
    actions: list[dict],
    gaps: list[dict],
) -> dict:
    """Generate suggestion for where a missing ingredient might be.
    
    Checks:
    1. Idle actions that might mention the ingredient visually
    2. Suspicious gaps where the addition could have happened
    
    Args:
        ingredient: Name of missing ingredient
        actions: All detected actions
        gaps: List of suspicious gaps
        
    Returns:
        Suggestion dict with nearest_candidate and suggestion text
    """
    # Check idle actions for visual clues
    idle_candidates = []
    for action in actions:
        if action.get("action_type") == "idle":
            desc = action.get("description", "").lower()
            # Check if description mentions colors/containers that might relate
            # (this is speculative, but better than nothing)
            if any(word in desc for word in ["spoon", "bowl", "hand", "powder", "spice"]):
                idle_candidates.append(action)
    
    # If we have gaps, suggest checking them
    if gaps:
        # Prefer gaps with "high" suspicion
        high_suspicion_gaps = [g for g in gaps if g.get("suspicion") == "high"]
        target_gaps = high_suspicion_gaps if high_suspicion_gaps else gaps[:3]
        
        return {
            "ingredient": ingredient,
            "nearest_candidate": target_gaps[0] if target_gaps else None,
            "suggestion": f"Check suspicious gap at {target_gaps[0]['start']:.1f}s ({target_gaps[0]['duration']:.0f}s long)" if target_gaps else "No obvious candidate found",
            "gap_count": len(target_gaps),
        }
    
    # Fallback: suggest checking idle moments
    if idle_candidates:
        return {
            "ingredient": ingredient,
            "nearest_candidate": idle_candidates[0],
            "suggestion": f"Check idle moment at {idle_candidates[0]['start_time']:.1f}s",
        }
    
    return {
        "ingredient": ingredient,
        "nearest_candidate": None,
        "suggestion": "No obvious candidate found in detected actions",
    }


async def reconcile_actions_with_recipe(
    all_actions: list[dict],
    recipe_context: dict,
    frame_results: list[Any],  # DenseFrameResult list (not used yet, reserved for future)
    video_path_map: dict[str, str],
) -> dict:
    """Compare detected actions against recipe to find missing ingredients.
    
    This is a pure text-matching service with NO LLM calls.
    
    Args:
        all_actions: List of detected action dicts
        recipe_context: Recipe with dish_name and recipe_steps
        frame_results: Dense frame extraction results (reserved for future gap re-scan)
        video_path_map: Map of video filename to full path
        
    Returns:
        {
            "matched_ingredients": [{"ingredient": "turmeric", "action_id": 5, "confidence": "high"}],
            "missing_ingredients": [{"ingredient": "garam masala", "suggestion": "..."}],
            "suspicious_gaps": [{"start": 129.0, "end": 169.0, "duration": 40.0, ...}],
        }
    """
    try:
        logger.info("Starting reconciliation: %d actions, recipe='%s'",
                    len(all_actions), recipe_context.get("dish_name", "Unknown"))
        
        # Step 1: Extract ingredients from recipe
        ingredients = extract_ingredients_from_recipe(recipe_context)
        
        if not ingredients:
            logger.warning("No ingredients extracted from recipe — skipping reconciliation")
            return {
                "matched_ingredients": [],
                "missing_ingredients": [],
                "suspicious_gaps": [],
                "status": "skipped_no_ingredients",
            }
        
        # Step 2: Match ingredients to actions
        matched, unmatched = match_ingredients_to_actions(ingredients, all_actions)
        
        # Step 3: Find suspicious gaps
        gaps = find_suspicious_gaps(all_actions, min_gap_seconds=10.0)
        
        # Step 4: Generate suggestions for missing ingredients
        missing_with_suggestions = []
        for item in unmatched:
            suggestion = suggest_missing_ingredient_location(
                item["ingredient"], all_actions, gaps
            )
            missing_with_suggestions.append(suggestion)
        
        result = {
            "matched_ingredients": matched,
            "missing_ingredients": missing_with_suggestions,
            "suspicious_gaps": gaps[:10],  # Limit to top 10
            "status": "completed",
            "total_ingredients": len(ingredients),
            "match_rate": round(len(matched) / len(ingredients) * 100, 1) if ingredients else 0,
        }
        
        logger.info("Reconciliation complete: %d matched, %d missing, %d gaps",
                    len(matched), len(missing_with_suggestions), len(gaps))
        
        return result
        
    except Exception as e:
        logger.exception("Reconciliation failed: %s", e)
        return {
            "matched_ingredients": [],
            "missing_ingredients": [],
            "suspicious_gaps": [],
            "status": "error",
            "error": str(e),
        }
