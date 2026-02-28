"""Select and order clips to tell a cooking narrative.

Two modes:
1. Recipe-step mode (preferred): When recipe_details contains numbered steps,
   parse them, extract keywords, and match chunks to steps IN ORDER.
2. Generic phase mode (fallback): Use hardcoded COOKING_PHASES when no
   structured recipe steps are available.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.models.project import EditDecision

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Generic cooking phases (fallback when recipe steps aren't available)
# ---------------------------------------------------------------------------
COOKING_PHASES = [
    {"name": "ingredients_prep", "label": "Preparing ingredients",
     "keywords": ["onion", "sliced", "chopping", "cutting", "ingredients", "knife",
                   "cutting board", "peeling", "dicing", "vegetables", "bread",
                   "banana", "slices", "preparing", "laid out", "arranged"],
     "max_clips": 1, "importance": 1.0},

    {"name": "spreading_mixing", "label": "Spreading/mixing",
     "keywords": ["spreading", "spread", "nutella", "chocolate spread", "jam",
                   "mashing", "mash", "fork", "spoon", "applying", "layer",
                   "paste", "sauce", "mixture", "ground", "mixed", "blended",
                   "peanut butter", "cream cheese"],
     "max_clips": 1, "importance": 1.2},

    {"name": "spice_seasoning", "label": "Seasoning/spices",
     "keywords": ["grinder", "spice", "grinding", "blender", "blending", "powder",
                   "turmeric", "coriander", "cumin", "curry leaves", "chili",
                   "seasoning", "salt", "pepper", "sugar", "sprinkle",
                   "marinate", "marinating", "coating", "coated"],
     "max_clips": 1, "importance": 1.2},

    {"name": "assembling", "label": "Assembling",
     "keywords": ["sandwich", "placing on top", "stacking", "assembling",
                   "another slice", "covering", "wrapping", "rolling",
                   "pressing", "together"],
     "max_clips": 1, "importance": 1.0},

    {"name": "heating_oil", "label": "Heating pan/oil/butter",
     "keywords": ["empty pan", "oil", "shimmering", "preheated", "heating",
                   "pouring oil", "hot oil", "melting butter", "butter melting",
                   "pat of butter", "melting"],
     "max_clips": 0, "importance": 0.8},

    {"name": "cooking_main", "label": "Cooking",
     "keywords": ["frying", "cooking", "sizzle", "sauteing", "stir-fry",
                   "stirring", "adding", "steam", "simmering", "boiling",
                   "frying pan", "cookeded", "cooked", "toasting", "toast",
                   "grilling", "baking", "roasting", "flipping"],
     "max_clips": 1, "importance": 2.0},

    {"name": "cooking_detail", "label": "Cooking close-ups / milk / caramel",
     "keywords": ["golden brown", "crispy", "close-up",
                   "crunchy", "sizzling", "bubbling", "caramel",
                   "caramelize", "soaking", "foam", "milk",
                   "foamy", "absorb", "poured", "milk poured",
                   "with milk"],
     "max_clips": 1, "importance": 4.0},

    {"name": "garnishing", "label": "Garnishing/finishing",
     "keywords": ["garnish", "herbs", "green leaves", "chili peppers", "lemon",
                   "squeezing", "drizzle", "topping", "sprinkle sugar",
                   "powdered sugar", "syrup", "honey", "caramel",
                   "spoon", "pressing", "butter on top"],
     "max_clips": 1, "importance": 1.0},

    {"name": "plating", "label": "Final dish/serving",
     "keywords": ["plating", "serving", "presentation", "ready", "final dish",
                   "plate", "white plate", "served", "finished dish",
                   "enjoy", "cut in half", "cross section", "piece of toast",
                   "toast is placed on a white plate"],
     "max_clips": 1, "importance": 1.5},
]


# ---------------------------------------------------------------------------
# Recipe step parsing
# ---------------------------------------------------------------------------

# Common cooking-related words that VL models use in descriptions
_KEYWORD_EXPANSIONS: dict[str, list[str]] = {
    "banana": ["banana", "bananas", "banana slices", "sliced banana", "banana slice"],
    "bread": ["bread", "slice of bread", "white bread", "slices of bread"],
    "fork": ["fork", "using a fork", "with a fork"],
    "mash": ["mash", "mashing", "mashed", "spreading", "pressing", "crush"],
    "nutella": ["nutella", "chocolate spread", "chocolate", "chocolate spread"],
    "spread": ["spread", "spreading", "applied", "applying", "layer"],
    "sandwich": ["sandwich", "on top", "stacking", "assembling", "placing on top", "place on top"],
    "pan": ["pan", "frying pan", "non-stick", "skillet"],
    "butter": ["butter", "pat of butter", "melting butter", "butter melting", "melting"],
    "toast": ["toast", "toasted", "toasting", "golden", "golden brown", "crispy", "crisp", "grilled"],
    "milk": ["milk", "white liquid", "foamy", "foam", "bubbling", "absorb", "absorbing", "poured"],
    "sugar": ["sugar", "caramel", "caramelize", "caramelized", "sprinkle", "amber", "glossy"],
    "spoon": ["spoon", "pressing", "press", "heated spoon"],
    "serve": ["serve", "serving", "plate", "plating", "plated", "ready", "final", "finished"],
    "heat": ["heat", "heating", "hot", "preheated", "melting"],
    "slice": ["slice", "sliced", "slicing", "cut", "cutting"],
    "place": ["place", "placing", "placed", "put", "laying", "laid"],
    "pour": ["pour", "pouring", "poured", "adding liquid"],
    "flip": ["flip", "flipping", "flipped", "turning", "both sides"],
}


def _parse_recipe_steps(recipe_details: str) -> list[dict[str, Any]]:
    """Parse numbered recipe steps from recipe_details text.
    
    Handles formats like:
    - "1. Do something"
    - "Step 1: Do something"
    - "1) Do something"
    
    Strips preamble (ingredients, method header) and skips trivial steps.
    Returns list of dicts with 'label', 'text', 'keywords' for each step.
    """
    if not recipe_details:
        return []
    
    text = recipe_details
    
    # Strip ingredients preamble — everything before "Method:" or first numbered step
    method_match = re.search(r'(?:method|directions|steps|instructions)\s*[:\.]\s*', text, re.IGNORECASE)
    if method_match:
        text = text[method_match.end():]
    
    # Try to split by numbered patterns
    # Match: "1. ", "1) ", "Step 1: ", "Step 1. ", etc.
    # Use \s to also match mid-line (not just start of line)
    step_pattern = r'(?:^|\n|\s)\s*(?:step\s*)?\d+[\.\):\-]\s*'
    parts = re.split(step_pattern, text, flags=re.IGNORECASE)
    
    # First part is preamble if it doesn't look like a step
    steps_text = [p.strip() for p in parts if p.strip()]
    
    # If the first part is short or looks like a header, skip it
    if steps_text and (len(steps_text[0]) < 15 or 
                        steps_text[0].lower().startswith(('ingredient', 'method', 'direction'))):
        steps_text = steps_text[1:]
    
    if len(steps_text) < 2:
        # Try splitting by sentences if no numbered steps found
        sentences = re.split(r'(?<=[.!])\s+', recipe_details)
        if len(sentences) >= 3:
            steps_text = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 20]
    
    if len(steps_text) < 2:
        return []  # Not enough structure, fall back to generic phases
    
    # Filter out trivial/repetition steps
    trivial_patterns = [r'^repeat\b', r'^if you.?re making', r'^do the same']
    steps_text = [s for s in steps_text 
                  if not any(re.match(p, s, re.IGNORECASE) for p in trivial_patterns)]
    
    # Split long steps that contain multiple distinct actions (separated by periods)
    expanded_steps = []
    for text in steps_text:
        # Split on sentence boundaries within a step, but only if they describe different actions
        sentences = [s.strip() for s in re.split(r'(?<=[.!])\s+', text) if s.strip() and len(s.strip()) > 15]
        if len(sentences) > 1:
            # Check if sentences have different keywords — if so, split
            for sent in sentences:
                # Skip trailing "Serve hot and enjoy" type fragments
                if re.match(r'^serve\b', sent, re.IGNORECASE) and len(sent) < 30:
                    expanded_steps.append(sent)  # Keep as separate serving step
                else:
                    expanded_steps.append(sent)
        else:
            expanded_steps.append(text)
    
    steps_text = expanded_steps
    
    recipe_steps = []
    for i, text in enumerate(steps_text):
        keywords = _extract_keywords(text)
        if not keywords:
            continue  # Skip steps with no extractable keywords
        recipe_steps.append({
            "label": f"Step {i + 1}: {text[:60]}{'...' if len(text) > 60 else ''}",
            "text": text,
            "keywords": keywords,
            "max_clips": 1,
        })
    
    # Always add a serving/plating step at the end if not already there
    last_text = steps_text[-1].lower() if steps_text else ""
    if not any(w in last_text for w in ["serve", "plate", "plating", "enjoy"]):
        recipe_steps.append({
            "label": "Serving/plating",
            "text": "serve plate final dish presentation",
            "keywords": ["serve", "serving", "plate", "plating", "final", "ready",
                         "finished", "presentation", "white plate", "enjoy"],
            "max_clips": 1,
        })
    
    return recipe_steps


def _extract_keywords(step_text: str) -> list[str]:
    """Extract matching keywords from a recipe step using expansions.
    
    For example, "mash banana with a fork" yields:
    ['mash', 'mashing', 'mashed', 'spreading', 'pressing', 'crush',
     'banana', 'bananas', 'banana slices', ..., 'fork', 'using a fork', ...]
    """
    text_lower = step_text.lower()
    keywords = set()
    
    for base_word, expansions in _KEYWORD_EXPANSIONS.items():
        if base_word in text_lower:
            keywords.update(expansions)
    
    # Also add significant words from the step itself (4+ chars, not stopwords)
    stopwords = {"with", "from", "that", "this", "then", "them", "they", "have",
                 "been", "will", "just", "enough", "make", "some", "into",
                 "until", "once", "don't", "it's", "very", "also", "more",
                 "another", "both", "little", "gently", "nicely", "repeat"}
    words = re.findall(r'[a-z]+', text_lower)
    for w in words:
        if len(w) >= 4 and w not in stopwords:
            keywords.add(w)
    
    return list(keywords)


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


# Distinctive tools/actions that strongly identify a specific recipe step.
# If a recipe step mentions one of these, chunks containing it get a big boost.
_DISTINCTIVE_MARKERS = {
    "fork": 8.0,
    "spoon": 5.0,
    "knife": 5.0,
    "spatula": 4.0,
    "tongs": 4.0,
    "grinder": 5.0,
    "blender": 5.0,
    "nutella": 6.0,
    "chocolate spread": 6.0,
    "milk": 6.0,
    "sugar": 6.0,
    "caramel": 6.0,
    "plate": 8.0,
    "serve": 8.0,
    "enjoy": 5.0,
}


def _score_chunk_for_step(analysis: dict[str, Any], step: dict[str, Any]) -> float:
    """Score how well a chunk matches a recipe step."""
    desc = analysis.get("description", "").lower()
    tags = [t.lower() for t in analysis.get("tags", [])]
    all_text = desc + " " + " ".join(tags)
    step_text = step.get("text", "").lower()
    step_all_text = step_text + " " + " ".join(step.get("keywords", []))
    
    score = 0.0
    
    # Base keyword matching
    for kw in step["keywords"]:
        if kw in all_text:
            score += 1.0
    
    # Distinctive marker bonus: if the recipe step mentions a specific tool/ingredient
    # AND the chunk description also mentions it, give a big boost.
    # This ensures "fork" in step → chunk with "fork" wins over generic banana chunk.
    # Check against step_all_text (includes expanded keywords) for broader matching.
    for marker, bonus in _DISTINCTIVE_MARKERS.items():
        if marker in step_all_text and marker in all_text:
            score += bonus
    
    # Cross-match synonyms: recipe says "nutella" but VL model says "chocolate spread"
    _SYNONYM_PAIRS = [
        (["nutella"], ["chocolate spread", "spreading chocolate"]),
        (["chocolate spread"], ["nutella", "spreading chocolate"]),
        (["sugar"], ["caramel", "caramelize", "caramelized", "amber", "sprinkle",
                     "spreading butter on toast", "spreading butter on a piece of toast"]),
        (["caramel"], ["sugar", "sprinkle", "spreading butter on toast",
                       "pressing", "heated", "spoon"]),
        (["milk"], ["white liquid", "foamy liquid", "foamy", "foam"]),
        # VL model sometimes misidentifies sugar sprinkling as "butter spreading"
        # when it sees a spoon on toast — add cross-match
        (["sprinkle"], ["spreading", "spoon", "toast"]),
    ]
    for recipe_words, desc_words in _SYNONYM_PAIRS:
        if any(rw in step_text for rw in recipe_words):
            if any(dw in all_text for dw in desc_words):
                score += 5.0
    
    # Penalty: if the step has distinctive markers but the chunk doesn't mention
    # ANY of them (or their synonyms), reduce score. This prevents generic chunks
    # from winning over specific ones just because they match more common keywords.
    _MARKER_SYNONYMS = {
        "fork": ["fork"],
        "spoon": ["spoon"],
        "nutella": ["nutella", "chocolate spread", "spreading chocolate", "spreading a chocolate"],
        "milk": ["milk", "white liquid", "foamy"],
        "sugar": ["sugar", "caramel", "caramelize", "caramelized", "amber"],
        "butter": ["butter", "melting butter", "pat of butter"],
        "plate": ["plate", "plating", "white plate"],
        "serve": ["plate", "plating", "served", "white plate", "finished"],
    }
    step_has_markers = False
    chunk_has_any_marker = False
    for marker, synonyms in _MARKER_SYNONYMS.items():
        if marker in step_all_text:
            step_has_markers = True
            if any(syn in all_text for syn in synonyms):
                chunk_has_any_marker = True
                break
    
    if step_has_markers and not chunk_has_any_marker:
        score *= 0.6  # Moderate penalty — VL models sometimes misidentify ingredients
    
    # Bonus for action words (verbs that show something happening)
    action_words = ["spreading", "mashing", "pouring", "placing", "cooking",
                    "frying", "toasting", "pressing", "holding", "using",
                    "preparing", "adding", "melting", "flipping", "stirring"]
    for w in action_words:
        if w in all_text:
            score += 0.5
    
    # Bonus for human presence (more interesting visually)
    if "person" in all_text or "hand" in all_text:
        score += 0.3
    
    return score


def _is_garbage(analysis: dict[str, Any]) -> bool:
    """Check if analysis is garbage."""
    desc = analysis.get("description", "")
    tags = analysis.get("tags", [])
    if not tags and ("!!!!" in desc or len(desc) < 10):
        return True
    return False


# ---------------------------------------------------------------------------
# Main selection logic
# ---------------------------------------------------------------------------

def select_clips(
    analyses: list[dict[str, Any]],
    recipe_details: str,
    dish_name: str,
    instructions: str,
    output_duration: int,
) -> list[EditDecision]:
    """Select clips following the recipe step order.
    
    If recipe_details contains numbered steps, uses recipe-step mode.
    Otherwise falls back to generic cooking phase mode.
    """
    if not analyses:
        return []

    valid = [a for a in analyses if not _is_garbage(a)]
    logger.info("Valid analyses: %d/%d", len(valid), len(analyses))

    # Try recipe-step mode first
    recipe_steps = _parse_recipe_steps(recipe_details)
    
    if recipe_steps:
        logger.info("Using recipe-step mode with %d steps", len(recipe_steps))
        return _select_by_recipe_steps(valid, recipe_steps, output_duration)
    else:
        logger.info("No recipe steps found, using generic phase mode")
        return _select_by_generic_phases(valid, recipe_details, output_duration)


def _select_by_recipe_steps(
    valid: list[dict[str, Any]],
    recipe_steps: list[dict[str, Any]],
    output_duration: int,
) -> list[EditDecision]:
    """Select one best chunk per recipe step, in recipe order.
    
    Budget-aware: if there are more steps than available slots, we first do
    a preliminary allocation to see which steps would be redundant (same
    source clip + nearby timestamp), then merge/skip those to make room for
    later steps.
    """
    
    chunk_dur_est = 10.0  # typical chunk duration
    max_slots = max(1, int(output_duration / chunk_dur_est))
    
    # Phase 1: Score every step's best chunk (without committing)
    step_candidates: list[tuple[int, float, dict[str, Any]]] = []  # (step_idx, score, chunk)
    temp_used: set[tuple] = set()
    
    for step_idx, step in enumerate(recipe_steps):
        scored: list[tuple[float, dict[str, Any]]] = []
        for a in valid:
            chunk_key = (a.get("clip_id"), a.get("segment_index"), a.get("chunk_index"))
            if chunk_key in temp_used:
                continue
            score = _score_chunk_for_step(a, step)
            if score > 0:
                scored.append((score, a))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        
        if scored:
            best_score, best_chunk = scored[0]
            chunk_key = (best_chunk.get("clip_id"), best_chunk.get("segment_index"), best_chunk.get("chunk_index"))
            temp_used.add(chunk_key)
            step_candidates.append((step_idx, best_score, best_chunk))
        else:
            logger.warning("No chunks match step %d: %s", step_idx, step["label"])
    
    # Phase 2: If more candidates than slots, prune redundant ones
    if len(step_candidates) > max_slots:
        step_candidates = _prune_redundant(step_candidates, max_slots, recipe_steps)
    
    # Phase 3: Build decisions from surviving candidates
    decisions: list[EditDecision] = []
    used_chunks: set[tuple] = set()
    total_duration = 0.0
    
    for step_idx, best_score, best_chunk in step_candidates:
        chunk_key = (best_chunk.get("clip_id"), best_chunk.get("segment_index"), best_chunk.get("chunk_index"))
        if chunk_key in used_chunks:
            continue
        used_chunks.add(chunk_key)
        
        chunk_dur = best_chunk.get("end_time", 10.0) - best_chunk.get("start_time", 0.0)
        if chunk_dur <= 0:
            chunk_dur = 10.0
        
        step = recipe_steps[step_idx]
        decisions.append(EditDecision(
            project_id="",
            sequence_order=len(decisions),
            source_clip_id=best_chunk.get("clip_id", ""),
            start_time=float(best_chunk.get("start_time", 0)),
            end_time=float(best_chunk.get("end_time", chunk_dur)),
            reason=f"{step['label']} | Score: {best_score:.1f}",
        ))
        total_duration += chunk_dur
        
        logger.info("Step %d: %s → chunk [%s %.0f-%.0fs] score=%.1f desc=%s",
                     step_idx, step["label"][:40],
                     best_chunk.get("clip_id", "")[:8],
                     best_chunk.get("start_time", 0),
                     best_chunk.get("end_time", 0),
                     best_score,
                     best_chunk.get("description", "")[:80])
    
    # Phase 4: Fill remaining budget with highest-scoring unused chunks
    if total_duration < output_duration:
        remaining: list[tuple[float, dict, int]] = []
        for a in valid:
            chunk_key = (a.get("clip_id"), a.get("segment_index"), a.get("chunk_index"))
            if chunk_key in used_chunks:
                continue
            max_score = 0.0
            best_step = 0
            for si, step in enumerate(recipe_steps):
                s = _score_chunk_for_step(a, step)
                if s > max_score:
                    max_score = s
                    best_step = si
            if max_score > 0:
                remaining.append((max_score, a, best_step))
        
        remaining.sort(key=lambda x: x[0], reverse=True)
        
        for score, a, step_idx in remaining:
            if total_duration >= output_duration:
                break
            chunk_key = (a.get("clip_id"), a.get("segment_index"), a.get("chunk_index"))
            if chunk_key in used_chunks:
                continue
            chunk_dur = a.get("end_time", 10.0) - a.get("start_time", 0.0)
            if chunk_dur <= 0:
                chunk_dur = 10.0
            used_chunks.add(chunk_key)
            decisions.append(EditDecision(
                project_id="",
                sequence_order=len(decisions),
                source_clip_id=a.get("clip_id", ""),
                start_time=float(a.get("start_time", 0)),
                end_time=float(a.get("end_time", chunk_dur)),
                reason=f"Fill ({recipe_steps[step_idx]['label'][:40]}) | Score: {score:.1f}",
            ))
            total_duration += chunk_dur
    
    # Final sequence order
    for i, d in enumerate(decisions):
        d.sequence_order = i
    
    logger.info("Selected %d clips (~%.0fs) for %ds target", len(decisions), total_duration, output_duration)
    return decisions


def _prune_redundant(
    candidates: list[tuple[int, float, dict[str, Any]]],
    max_slots: int,
    recipe_steps: list[dict[str, Any]],
) -> list[tuple[int, float, dict[str, Any]]]:
    """Prune redundant candidates when we have more steps than slots.
    
    Strategy: detect pairs of consecutive steps that selected chunks from 
    the same source clip with similar content. Merge them by keeping only 
    the higher-scoring one. Repeat until we fit within max_slots.
    """
    result = list(candidates)
    
    while len(result) > max_slots:
        # Find the most redundant adjacent pair
        best_merge_idx = -1
        best_merge_score_loss = float('inf')
        
        for i in range(len(result) - 1):
            si_a, score_a, chunk_a = result[i]
            si_b, score_b, chunk_b = result[i + 1]
            
            # Same source clip = likely redundant
            same_clip = chunk_a.get("clip_id") == chunk_b.get("clip_id")
            # Close timestamps = likely redundant
            time_diff = abs(chunk_a.get("start_time", 0) - chunk_b.get("start_time", 0))
            close_time = time_diff < 60
            
            # Check keyword overlap between the two steps
            kw_a = set(recipe_steps[si_a].get("keywords", []))
            kw_b = set(recipe_steps[si_b].get("keywords", []))
            overlap = len(kw_a & kw_b) / max(len(kw_a | kw_b), 1)
            
            redundancy = 0.0
            if same_clip and close_time:
                redundancy = 3.0
            elif same_clip:
                redundancy = 2.0
            elif close_time:
                redundancy = 1.0
            redundancy += overlap * 2.0
            
            # Score loss = the weaker score of the pair
            score_loss = min(score_a, score_b) - redundancy * 2.0
            
            if score_loss < best_merge_score_loss:
                best_merge_score_loss = score_loss
                best_merge_idx = i
        
        if best_merge_idx < 0:
            # No good merges — just drop the lowest-scoring candidate
            min_idx = min(range(len(result)), key=lambda i: result[i][1])
            result.pop(min_idx)
        else:
            # Keep the higher-scoring one of the pair
            si_a, score_a, chunk_a = result[best_merge_idx]
            si_b, score_b, chunk_b = result[best_merge_idx + 1]
            if score_a >= score_b:
                result.pop(best_merge_idx + 1)
            else:
                result.pop(best_merge_idx)
    
    return result


def _select_by_generic_phases(
    valid: list[dict[str, Any]],
    recipe_details: str,
    output_duration: int,
) -> list[EditDecision]:
    """Fallback: select clips using generic cooking phases."""
    
    # Classify each chunk
    phase_buckets: dict[int, list[tuple[float, dict]]] = {}

    for a in valid:
        matches = _classify_phase_generic(a)
        quality = _visual_quality_score(a)
        
        if matches:
            best_phase, best_score = matches[0]
            combined = best_score + quality
            phase_buckets.setdefault(best_phase, []).append((combined, a))

    for idx in phase_buckets:
        phase_buckets[idx].sort(key=lambda x: x[0], reverse=True)

    decisions: list[EditDecision] = []
    total_duration = 0.0
    used_chunks: set[tuple] = set()

    for phase_idx in range(len(COOKING_PHASES)):
        if phase_idx not in phase_buckets:
            continue

        phase = COOKING_PHASES[phase_idx]
        bucket = phase_buckets[phase_idx]
        clips_added = 0

        for score, a in bucket:
            if clips_added >= phase["max_clips"]:
                break

            chunk_key = (a.get("clip_id"), a.get("segment_index"), a.get("chunk_index"))
            if chunk_key in used_chunks:
                continue

            chunk_dur = a.get("end_time", 15.0) - a.get("start_time", 0.0)
            if chunk_dur <= 0:
                chunk_dur = 15.0

            used_chunks.add(chunk_key)
            clips_added += 1
            decisions.append(EditDecision(
                project_id="",
                sequence_order=len(decisions),
                source_clip_id=a.get("clip_id", ""),
                start_time=float(a.get("start_time", 0)),
                end_time=float(a.get("end_time", chunk_dur)),
                reason=f"Phase: {phase['label']} | Score: {score:.1f}",
            ))
            total_duration += chunk_dur

    # Fill remaining
    if total_duration < output_duration:
        remaining = []
        for phase_idx, bucket in phase_buckets.items():
            for score, a in bucket:
                chunk_key = (a.get("clip_id"), a.get("segment_index"), a.get("chunk_index"))
                if chunk_key not in used_chunks:
                    remaining.append((score, a, phase_idx))
        remaining.sort(key=lambda x: x[0], reverse=True)

        for score, a, phase_idx in remaining:
            if total_duration >= output_duration:
                break
            chunk_key = (a.get("clip_id"), a.get("segment_index"), a.get("chunk_index"))
            if chunk_key in used_chunks:
                continue
            chunk_dur = a.get("end_time", 15.0) - a.get("start_time", 0.0)
            if chunk_dur <= 0:
                chunk_dur = 15.0
            used_chunks.add(chunk_key)
            decisions.append(EditDecision(
                project_id="",
                sequence_order=len(decisions),
                source_clip_id=a.get("clip_id", ""),
                start_time=float(a.get("start_time", 0)),
                end_time=float(a.get("end_time", chunk_dur)),
                reason=f"Fill ({COOKING_PHASES[phase_idx]['label']}) | Score: {score:.1f}",
            ))
            total_duration += chunk_dur

    for i, d in enumerate(decisions):
        d.sequence_order = i

    logger.info("Selected %d clips (~%.0fs) for %ds target", len(decisions), total_duration, output_duration)
    return decisions


def _classify_phase_generic(analysis: dict[str, Any]) -> list[tuple[int, float]]:
    """Classify a chunk into generic cooking phases."""
    desc = analysis.get("description", "").lower()
    tags = [t.lower() for t in analysis.get("tags", [])]
    all_text = desc + " " + " ".join(tags)

    matches = []
    for i, phase in enumerate(COOKING_PHASES):
        score = 0.0
        for kw in phase["keywords"]:
            if kw in all_text:
                score += 1.0
        if score > 0:
            matches.append((i, score * phase["importance"]))

    matches.sort(key=lambda x: x[1], reverse=True)
    return matches


def _visual_quality_score(analysis: dict[str, Any]) -> float:
    """Score visual interestingness."""
    desc = analysis.get("description", "").lower()
    tags = [t.lower() for t in analysis.get("tags", [])]
    all_text = desc + " " + " ".join(tags)
    score = len(tags) * 0.3

    for w in ["stirring", "pouring", "adding", "squeezing", "cooking", "frying",
              "holding", "placing", "using", "preparing"]:
        if w in all_text:
            score += 1.0
    for w in ["colorful", "bright", "golden", "steam", "sizzle", "crispy"]:
        if w in all_text:
            score += 0.8
    if "person" in all_text or "hand" in all_text:
        score += 0.5
    return score
