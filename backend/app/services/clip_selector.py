"""Clip selection with coverage guarantee, MMR diversity, and speed ramps.

Takes Pass 1 analysis results and produces an ordered edit decision list
ensuring every recipe step is represented with diverse, high-quality clips.
"""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import Any

from app.models.project import EditDecision

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Recipe step matching
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Lowercase and strip punctuation."""
    return re.sub(r'[^\w\s]', '', text.lower()).strip()


def _keyword_overlap(text_a: str, text_b: str) -> float:
    """Compute keyword overlap ratio between two texts."""
    words_a = set(_normalize(text_a).split())
    words_b = set(_normalize(text_b).split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    return len(intersection) / min(len(words_a), len(words_b))


def _fuzzy_match_score(scene_desc: str, step_text: str, scene_phase: str, step_phase: str) -> float:
    """Score how well a scene matches a recipe step using multiple signals."""
    score = 0.0

    # 1. Keyword overlap
    kw_score = _keyword_overlap(scene_desc, step_text)
    score += kw_score * 5.0

    # 2. Sequence matcher similarity
    seq_score = SequenceMatcher(None, _normalize(scene_desc), _normalize(step_text)).ratio()
    score += seq_score * 3.0

    # 3. Phase bonus — if scene phase matches step's expected phase
    if scene_phase and step_phase and scene_phase == step_phase:
        score += 2.0

    # 4. Direct step number match (from Claude's tagging)
    # This is handled externally since we use recipe_step_number

    return score


# ---------------------------------------------------------------------------
# Speed ramp heuristics
# ---------------------------------------------------------------------------

# Actions that should be sped up
_SPEEDUP_KEYWORDS = {
    "stirring": 3.0, "stir": 3.0, "mixing": 2.5, "mix": 2.5,
    "boiling": 4.0, "simmering": 4.0, "waiting": 4.0,
    "kneading": 2.5, "whisking": 2.5, "whisk": 2.5,
    "resting": 4.0, "rising": 4.0, "cooling": 4.0,
    "chopping": 2.0, "dicing": 2.0, "mincing": 2.0,
}

# Actions that should be slow-mo
_SLOWMO_KEYWORDS = {
    "plating": 0.75, "plate": 0.75, "serving": 0.75,
    "drizzle": 0.75, "drizzling": 0.75, "pouring": 0.8,
    "sizzle": 0.75, "sizzling": 0.75,
    "slicing": 0.8, "cutting": 0.85,
    "reveal": 0.75, "garnish": 0.8, "garnishing": 0.8,
    "finished": 0.75, "final": 0.75,
}


def _compute_speed_factor(description: str, action: str, phase: str) -> float:
    """Determine speed factor for a clip based on its content."""
    text = f"{description} {action}".lower()

    # Check slow-mo first (takes priority for hero moments)
    if phase == "plate":
        return 0.75

    for keyword, factor in _SLOWMO_KEYWORDS.items():
        if keyword in text:
            return factor

    for keyword, factor in _SPEEDUP_KEYWORDS.items():
        if keyword in text:
            return factor

    return 1.0


# ---------------------------------------------------------------------------
# MMR Diversity Selection
# ---------------------------------------------------------------------------

def _scene_similarity(scene_a: dict, scene_b: dict) -> float:
    """Compute similarity between two scenes for diversity scoring."""
    sim = 0.0

    # Description overlap
    desc_a = scene_a.get("description", "")
    desc_b = scene_b.get("description", "")
    if desc_a and desc_b:
        sim += SequenceMatcher(None, _normalize(desc_a), _normalize(desc_b)).ratio() * 0.4

    # Same scene type
    if scene_a.get("scene_type") == scene_b.get("scene_type"):
        sim += 0.2

    # Temporal proximity (closer = more similar)
    time_diff = abs(scene_a.get("start_time", 0) - scene_b.get("start_time", 0))
    if time_diff < 30:
        sim += 0.3 * (1.0 - time_diff / 30.0)

    # Same shot type
    if scene_a.get("shot_type") == scene_b.get("shot_type"):
        sim += 0.1

    return min(sim, 1.0)


def _mmr_select(candidates: list[dict], selected: list[dict], lambda_param: float = 0.5) -> dict | None:
    """Select next best candidate using Maximal Marginal Relevance."""
    if not candidates:
        return None

    best_score = -float('inf')
    best_idx = 0

    for i, cand in enumerate(candidates):
        relevance = cand.get("edit_value", 5.0) / 10.0

        if selected:
            max_sim = max(_scene_similarity(cand, s) for s in selected)
        else:
            max_sim = 0.0

        score = lambda_param * relevance - (1 - lambda_param) * max_sim

        if score > best_score:
            best_score = score
            best_idx = i

    return candidates[best_idx]


# ---------------------------------------------------------------------------
# Main selection algorithm
# ---------------------------------------------------------------------------

def select_clips_v2(
    pass1_results: list[dict],
    scenes_metadata: list[dict],
    recipe_context: dict,
    target_duration: float = 60.0,
    pass2_decisions: dict | None = None,
) -> list[dict]:
    """Select clips using Pass 2 decisions or fallback to algorithmic selection.
    
    If pass2_decisions is provided (from Claude Pass 2), use those directly.
    Otherwise, run algorithmic selection as fallback.
    
    Returns list of dicts with: scene_index, start_time, end_time, duration,
    speed_factor, recipe_step, recipe_phase, description, reason.
    """
    if pass2_decisions and pass2_decisions.get("edit_decision_list"):
        return _use_pass2_decisions(pass2_decisions, scenes_metadata)

    return _algorithmic_select(pass1_results, scenes_metadata, recipe_context, target_duration)


def _use_pass2_decisions(pass2: dict, scenes_metadata: list[dict]) -> list[dict]:
    """Convert Pass 2 Claude decisions to our clip format."""
    clips = []
    for d in pass2.get("edit_decision_list", []):
        scene_idx = d.get("scene_index", 0)
        meta = next((m for m in scenes_metadata if m["scene_index"] == scene_idx), {})

        clips.append({
            "scene_index": scene_idx,
            "source_video": meta.get("source_video", ""),
            "clip_id": meta.get("clip_id", ""),
            "start_time": d.get("start_time", meta.get("start_time", 0)),
            "end_time": d.get("end_time", meta.get("end_time", 0)),
            "duration": d.get("duration", 0),
            "speed_factor": d.get("speed_factor", 1.0),
            "recipe_step": d.get("recipe_step"),
            "recipe_phase": d.get("recipe_phase", ""),
            "description": d.get("description", ""),
            "reason": d.get("why_selected", ""),
        })

    return clips


def _algorithmic_select(
    pass1_results: list[dict],
    scenes_metadata: list[dict],
    recipe_context: dict,
    target_duration: float,
) -> list[dict]:
    """Fallback algorithmic selection with coverage guarantee + MMR diversity."""
    recipe_steps = recipe_context.get("recipe_steps", [])
    n_steps = len(recipe_steps)
    if n_steps == 0:
        return _select_by_quality(pass1_results, scenes_metadata, target_duration)

    # Build enriched scene data by merging Pass 1 results with metadata
    enriched_scenes = []
    for p1, meta in zip(pass1_results, scenes_metadata):
        summary = p1.get("scene_summary", {})
        enriched_scenes.append({
            **meta,
            "edit_value": summary.get("overall_edit_value", 0),
            "primary_step": summary.get("primary_step_number"),
            "steps_covered": summary.get("steps_covered", []),
            "dominant_phase": summary.get("dominant_phase", "unknown"),
            "description": summary.get("description", ""),
            "has_transition": summary.get("has_transition", False),
            "best_frame_index": summary.get("best_frame_index", 0),
            "shot_type": _get_dominant_shot_type(p1),
        })

    # Phase 1: Bucket scenes by recipe step
    step_buckets: dict[int, list[dict]] = {i + 1: [] for i in range(n_steps)}
    unassigned = []

    for scene in enriched_scenes:
        assigned = False
        # Use Claude's step tagging first
        if scene.get("primary_step"):
            step_num = scene["primary_step"]
            if step_num in step_buckets:
                step_buckets[step_num].append(scene)
                assigned = True

        # Also add to other covered steps
        for step_num in scene.get("steps_covered", []):
            if step_num in step_buckets and scene not in step_buckets[step_num]:
                step_buckets[step_num].append(scene)
                assigned = True

        # Fuzzy match fallback
        if not assigned:
            best_step = None
            best_score = 0
            desc = scene.get("description", "")
            phase = scene.get("dominant_phase", "")
            for i, step_text in enumerate(recipe_steps, 1):
                step_phase = _infer_phase(i, n_steps)
                score = _fuzzy_match_score(desc, step_text, phase, step_phase)
                if score > best_score:
                    best_score = score
                    best_step = i
            if best_step and best_score > 1.5:
                step_buckets[best_step].append(scene)
            else:
                unassigned.append(scene)

    # Sort each bucket by edit_value descending
    for step_num in step_buckets:
        step_buckets[step_num].sort(key=lambda s: s.get("edit_value", 0), reverse=True)

    # Phase 2: Coverage-guaranteed selection (best scene per step)
    selected: list[dict] = []
    used_scenes: set[int] = set()
    used_dup_groups: set[int] = set()

    for step_num in sorted(step_buckets.keys()):
        bucket = step_buckets[step_num]
        chosen = None

        for scene in bucket:
            idx = scene["scene_index"]
            dup_group = scene.get("duplicate_group", -1)

            # Skip already used
            if idx in used_scenes:
                continue
            # Skip if duplicate group already represented
            if dup_group >= 0 and dup_group in used_dup_groups:
                continue

            chosen = scene
            break

        if chosen:
            used_scenes.add(chosen["scene_index"])
            if chosen.get("duplicate_group", -1) >= 0:
                used_dup_groups.add(chosen["duplicate_group"])

            phase = _infer_phase(step_num, n_steps)
            desc = chosen.get("description", "")
            action = desc  # use description as action text for speed calc
            speed = _compute_speed_factor(desc, action, chosen.get("dominant_phase", phase))

            selected.append({
                "scene_index": chosen["scene_index"],
                "source_video": chosen.get("source_video", ""),
                "clip_id": chosen.get("clip_id", ""),
                "start_time": chosen["start_time"],
                "end_time": chosen["end_time"],
                "duration": chosen["end_time"] - chosen["start_time"],
                "speed_factor": speed,
                "recipe_step": step_num,
                "recipe_phase": chosen.get("dominant_phase", phase),
                "description": desc,
                "reason": f"Step {step_num} coverage (edit_value={chosen.get('edit_value', 0)})",
                "edit_value": chosen.get("edit_value", 0),
                "scene_type": chosen.get("scene_type", ""),
                "shot_type": chosen.get("shot_type", ""),
            })

    # Phase 3: Fill remaining duration with MMR diversity selection
    # BUT enforce strict visual diversity — no two clips with similar descriptions
    current_duration = sum(c["duration"] / c.get("speed_factor", 1.0) for c in selected)

    remaining_scenes = [s for s in enriched_scenes if s["scene_index"] not in used_scenes]
    remaining_scenes.sort(key=lambda s: s.get("edit_value", 0), reverse=True)

    while current_duration < target_duration and remaining_scenes:
        next_scene = _mmr_select(remaining_scenes, selected, lambda_param=0.3)
        if not next_scene:
            break

        idx = next_scene["scene_index"]
        dup_group = next_scene.get("duplicate_group", -1)

        # Skip if duplicate group already represented
        if dup_group >= 0 and dup_group in used_dup_groups:
            remaining_scenes.remove(next_scene)
            continue

        # Skip if too similar to any already selected clip (description-based)
        desc = next_scene.get("description", "")
        too_similar = False
        for existing in selected:
            ex_desc = existing.get("description", "")
            if desc and ex_desc:
                sim = SequenceMatcher(None, _normalize(desc), _normalize(ex_desc)).ratio()
                if sim > 0.6:
                    too_similar = True
                    break
            # Also check same recipe step — don't add more than 1 per step
            if (next_scene.get("primary_step") and
                next_scene.get("primary_step") == existing.get("recipe_step")):
                too_similar = True
                break

        if too_similar:
            remaining_scenes.remove(next_scene)
            continue

        used_scenes.add(idx)
        if dup_group >= 0:
            used_dup_groups.add(dup_group)

        phase = next_scene.get("dominant_phase", "unknown")
        speed = _compute_speed_factor(desc, desc, phase)

        selected.append({
            "scene_index": idx,
            "source_video": next_scene.get("source_video", ""),
            "clip_id": next_scene.get("clip_id", ""),
            "start_time": next_scene["start_time"],
            "end_time": next_scene["end_time"],
            "duration": next_scene["end_time"] - next_scene["start_time"],
            "speed_factor": speed,
            "recipe_step": next_scene.get("primary_step"),
            "recipe_phase": phase,
            "description": desc,
            "reason": f"MMR fill (edit_value={next_scene.get('edit_value', 0)})",
            "edit_value": next_scene.get("edit_value", 0),
            "scene_type": next_scene.get("scene_type", ""),
            "shot_type": next_scene.get("shot_type", ""),
        })

        current_duration += (next_scene["end_time"] - next_scene["start_time"]) / speed
        remaining_scenes.remove(next_scene)

    # Phase 4: Duration management — trim to target
    current_duration = sum(c["duration"] / c.get("speed_factor", 1.0) for c in selected)
    if current_duration > target_duration * 1.1:
        # Drop lowest edit_value non-sole clips
        step_counts: dict[int | None, int] = {}
        for c in selected:
            step = c.get("recipe_step")
            step_counts[step] = step_counts.get(step, 0) + 1

        while current_duration > target_duration * 1.1 and len(selected) > 1:
            # Find droppable clip (not the only one for its step)
            droppable = [
                (i, c) for i, c in enumerate(selected)
                if step_counts.get(c.get("recipe_step"), 0) > 1
            ]
            if not droppable:
                # All clips are sole representatives — trim durations instead
                break
            # Drop lowest edit_value
            droppable.sort(key=lambda x: x[1].get("edit_value", 0))
            drop_idx, drop_clip = droppable[0]
            step = drop_clip.get("recipe_step")
            if step is not None:
                step_counts[step] -= 1
            current_duration -= drop_clip["duration"] / drop_clip.get("speed_factor", 1.0)
            selected.pop(drop_idx)

    # Phase 5: Order chronologically by source video, then timestamp
    # The chef filmed in the correct order — respect that, don't reorder by recipe step
    selected.sort(key=lambda c: (c.get("source_video", ""), c["start_time"]))

    logger.info("Selected %d clips, ~%.1fs output (target %ds)", 
                len(selected), current_duration, int(target_duration))

    return selected


def _select_by_quality(
    pass1_results: list[dict],
    scenes_metadata: list[dict],
    target_duration: float,
) -> list[dict]:
    """Fallback: select by quality when no recipe steps provided."""
    enriched = []
    for p1, meta in zip(pass1_results, scenes_metadata):
        summary = p1.get("scene_summary", {})
        enriched.append({
            **meta,
            "edit_value": summary.get("overall_edit_value", 0),
            "description": summary.get("description", ""),
        })

    enriched.sort(key=lambda s: s.get("edit_value", 0), reverse=True)

    selected = []
    current_dur = 0.0
    used_dup = set()

    for scene in enriched:
        if current_dur >= target_duration:
            break
        dup = scene.get("duplicate_group", -1)
        if dup >= 0 and dup in used_dup:
            continue
        if dup >= 0:
            used_dup.add(dup)

        selected.append({
            "scene_index": scene["scene_index"],
            "source_video": scene.get("source_video", ""),
            "clip_id": scene.get("clip_id", ""),
            "start_time": scene["start_time"],
            "end_time": scene["end_time"],
            "duration": scene["end_time"] - scene["start_time"],
            "speed_factor": 1.0,
            "recipe_step": None,
            "recipe_phase": "unknown",
            "description": scene.get("description", ""),
            "reason": f"Quality select (edit_value={scene.get('edit_value', 0)})",
        })
        current_dur += scene["duration"]

    selected.sort(key=lambda c: c["start_time"])
    return selected


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _infer_phase(step_num: int, total_steps: int) -> str:
    """Infer recipe phase from step position."""
    ratio = step_num / total_steps
    if ratio <= 0.35:
        return "prep"
    elif ratio <= 0.8:
        return "cook"
    else:
        return "plate"


def _get_dominant_shot_type(pass1_result: dict) -> str:
    """Get the most common shot type from Pass 1 frames."""
    frames = pass1_result.get("frames", [])
    if not frames:
        return "unknown"
    shot_types = [f.get("composition", {}).get("shot_type", "unknown") for f in frames]
    if not shot_types:
        return "unknown"
    return max(set(shot_types), key=shot_types.count)


# ---------------------------------------------------------------------------
# Legacy API compat
# ---------------------------------------------------------------------------

def select_clips(
    analyses: list[dict[str, Any]],
    recipe_details: str,
    dish_name: str,
    instructions: str,
    output_duration: int,
) -> list[EditDecision]:
    """Legacy entry point — wraps old-style analyses into new format."""
    # This is kept for backward compatibility with the old pipeline
    # The new pipeline uses select_clips_v2 directly
    from app.services.clip_selector_legacy import select_clips as _legacy_select
    return _legacy_select(analyses, recipe_details, dish_name, instructions, output_duration)
