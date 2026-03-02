# Smart Clip Finding System — Design Doc

## Problem

When users ask to add/replace a clip in the refine chat (e.g., "add the garam masala scene"), the AI often can't find it. Root cause: action detection runs once during pipeline and misses or mislabels clips. A "garam masala" moment might be labeled "stirring pot" or missed entirely because it happened between two detected actions.

### Three Failure Modes

1. **Mislabeled clips** — The clip exists in the pool but has a generic description like "stirring pot" when it's actually "adding garam masala while stirring"
2. **Gaps between actions** — The moment falls in a time range between two detected actions, so no clip was extracted for it
3. **Overlapping actions** — The moment is buried INSIDE an existing clip's time range (e.g., spice added mid-stir), labeled only by the dominant action

## Solution: Layered Escalation System

Each layer is progressively more expensive. We stop as soon as we find what the user wants.

---

### Layer 0: Literal String Search
**Cost:** Zero (regex, no LLM)  
**Speed:** Instant

Before any LLM call, do a literal/fuzzy string search across ALL clip descriptions in the project.

```python
import re
# User says "garam masala"
keywords = ["garam", "masala"]
matches = [clip for clip in all_clips 
           if any(re.search(kw, clip["description"], re.IGNORECASE) for kw in keywords)]
```

**Why this exists:** Sometimes the clip IS correctly labeled but buried in a pool of 93 clips where the user didn't scroll far enough. This catches the "it was there all along" case for free.

**If found:** Return matches directly → done.  
**If not found:** Proceed to Layer 1.

---

### Layer 1: Semantic Re-Match (Current System)
**Cost:** Minimal (keyword boost + LLM matching against existing pool)  
**Speed:** ~2-3 seconds

This is what we have today. Send the user's description + clip pool to Claude. The keyword-boosted pool (top 50 clips) is searched semantically.

The current `REFINE_TOOL` with `propose` mode handles this — Claude picks the best candidates from the pool and either applies directly (high confidence) or proposes candidates with thumbnails (ambiguous).

**If found with high confidence:** Apply directly → done.  
**If ambiguous candidates exist (above confidence threshold):** Show proposal with thumbnails → user picks → done.  
**If no good candidates (nothing clears confidence bar):** Proceed to Layer 2 silently. Do NOT show garbage matches just to look like you're trying — it erodes trust.

---

### Layer 2: Visual Re-Check of Candidate Clips
**Cost:** Low-medium (extract frames from ~5-10 existing clips, one vision LLM call)  
**Speed:** ~10-15 seconds

Take the top semantic matches from Layer 1 — even if they scored low — and visually verify them. The description might say "stirring pot" but the actual frames might show garam masala being added.

```python
# For each candidate clip from Layer 1's low-confidence results:
# 1. Extract 3-5 frames from the clip's time range
# 2. Send frames to vision model with focused prompt:
#    "Does this clip show [user's description]? Look specifically for [keywords]."
# 3. If vision model confirms → we found it
```

**Why this works:** Catches Failure Mode 1 (mislabeled clips). The description was wrong, but the visual content matches.

**If found:** Return match → propose to user with thumbnail → done.  
**If not found:** Proceed to Layer 3.

---

### Layer 3: Targeted Re-Scan (Gaps + Generic Clips)
**Cost:** Medium-high (FFmpeg frame extraction + vision LLM on new frames)  
**Speed:** ~30-60 seconds

This is the heavy lift. We extract NEW frames from time ranges that weren't well-covered by initial action detection.

**TWO scan targets (this is critical):**

#### 3A: Gap Scanning
Scan time ranges BETWEEN existing detected actions where no clip was extracted.

```python
# Sort all clips by start_time per video
# Find gaps > 1 second between clip end_time and next clip start_time
# Extract frames from those gaps
```

Catches **Failure Mode 2** (gaps between actions).

#### 3B: Generic Clip Re-Scanning
Scan time ranges OF existing clips that have vague/generic descriptions like "stirring pot", "cooking on stove", "handling ingredients".

```python
# Filter clips with generic descriptions
generic_keywords = ["stirring", "cooking", "preparing", "handling", "mixing"]
generic_clips = [c for c in all_clips 
                 if any(kw in c["description"].lower() for kw in generic_keywords)]
# Extract additional frames from these clips' time ranges
# Use focused prompt: "Look for [user's specific description] happening during this scene"
```

Catches **Failure Mode 3** (overlapping actions). If someone tosses garam masala while stirring, the "stirring pot" clip at 2:00-2:15 is exactly where to look.

**For both scans, use a focused vision prompt:**
```
"Extract frames and look specifically for: [user's description].
This is a cooking video. The user is looking for a moment involving [keywords].
Describe what you see in each frame with focus on ingredients, spices, and actions."
```

**If found:** Create new clip entry, propose to user with thumbnail → done.  
**If not found:** Proceed to Layer 4.

---

### Layer 4: Full Video Re-Scan (Nuclear Option)
**Cost:** High (full re-detection on relevant video segments)  
**Speed:** ~2-5 minutes

Re-run the entire action detection pipeline on the source video, but with an ENHANCED prompt that specifically includes the user's search term.

```python
# Modified detection prompt:
# "Detect all cooking actions. Pay special attention to: [user's description].
#  Make sure to label spice additions specifically (e.g., 'adding garam masala' 
#  not just 'stirring')."
```

This is basically admitting the original detection was insufficient and re-doing it with more context. Expensive but thorough.

**If found:** Add new clips to pool, propose to user → done.  
**If not found:** Proceed to Layer 5.

---

### Layer 5: Honest Admission
**Cost:** Zero  
**Speed:** Instant

```
"I've searched through the entire video thoroughly and couldn't find a scene 
matching '[description]'. It's possible this moment wasn't captured in the 
footage, or it looks very different from what I'm searching for. 

You can try:
- Browsing the clip timeline manually to find it
- Describing the scene differently (what was happening around it?)
- Uploading the specific timestamp if you know it"
```

Don't hallucinate. Don't show garbage. Be honest.

---

## Architecture Overview

```
User: "add the garam masala scene"
         │
         ▼
   ┌─── Layer 0: Regex Search ───┐
   │  Found? ──► Return match     │
   │  Not found? ──► Continue     │
   └──────────────────────────────┘
         │
         ▼
   ┌─── Layer 1: Semantic Match ──┐
   │  High confidence? ──► Apply  │
   │  Ambiguous? ──► Propose      │
   │  Nothing good? ──► Continue  │
   └──────────────────────────────┘
         │
         ▼
   ┌─── Layer 2: Visual Re-Check ─┐
   │  Vision confirms? ──► Propose│
   │  No match? ──► Continue      │
   └──────────────────────────────┘
         │
         ▼
   ┌─── Layer 3: Re-Scan ─────────┐
   │  3A: Gaps between clips      │
   │  3B: Generic clip re-scan    │
   │  Found? ──► Create + Propose │
   │  Not found? ──► Continue     │
   └──────────────────────────────┘
         │
         ▼
   ┌─── Layer 4: Full Re-Detect ──┐
   │  Enhanced prompt re-scan     │
   │  Found? ──► Create + Propose │
   │  Not found? ──► Continue     │
   └──────────────────────────────┘
         │
         ▼
   ┌─── Layer 5: Honest Admission ┐
   │  "Couldn't find it"          │
   │  Offer alternatives          │
   └──────────────────────────────┘
```

## Implementation Priority

| Layer | Effort | Impact | Priority |
|-------|--------|--------|----------|
| 0 - Regex | 15 min | Catches "already there" cases | **Ship first** |
| 1 - Semantic | Already done | Current system | **Done** |
| 2 - Visual Re-Check | 2-3 hours | Catches mislabeled clips | **High** |
| 3 - Gap + Generic Re-Scan | 4-6 hours | Catches missed moments | **High** |
| 4 - Full Re-Detect | 2-3 hours | Nuclear fallback | **Medium** |
| 5 - Honest Admission | 30 min | UX polish | **Ship with Layer 0** |

**Recommended build order:** 0 → 5 → 2 → 3 → 4

Layer 0 and 5 are bookends — trivial to add, immediately improve UX. Layers 2 and 3 are the real value. Layer 4 is a last resort most users will never hit if 2+3 work well.

## Key Design Decisions

1. **Silent escalation** — Don't tell the user "searching harder..." at every layer. Just find it and present the result. Only surface status if Layer 3+ takes noticeable time (>5 seconds).

2. **Confidence threshold for proposals** — If semantic match returns candidates below a threshold, skip to next layer silently instead of showing bad matches. Showing garbage erodes trust more than a brief wait.

3. **Layer 3 scans BOTH gaps and generic clips** — This was a key insight. The original design only scanned gaps (time ranges with no clips). But Failure Mode 3 (overlapping actions) means the clip we want is INSIDE an existing clip's time range. Generic descriptions like "stirring pot" are prime candidates for hiding specific sub-actions.

4. **Focused prompts beat generic re-detection** — At Layer 3+, the vision prompt should specifically mention what we're looking for. "Find garam masala" beats "detect all cooking actions" for a targeted search.

5. **User can always browse manually** — The clip pool UI (with thumbnails) lets users find things visually when AI fails. This is the ultimate fallback and should always be available.

## Cost Estimates (per search escalation)

| Layer | API Cost | Time |
|-------|----------|------|
| 0 | $0.00 | <100ms |
| 1 | ~$0.01-0.02 | 2-3s |
| 2 | ~$0.02-0.05 | 10-15s |
| 3 | ~$0.05-0.15 | 30-60s |
| 4 | ~$0.20-0.50 | 2-5min |
| Total worst case | ~$0.30-0.70 | ~3-6min |

Most searches will resolve at Layer 0 or 1. Layer 3+ should be rare with good initial detection.

## Context: Why This Matters

Videopeen is a cooking video editor. Cooking videos have a specific challenge: many visually similar actions (stirring, adding ingredients) that differ only in what's being added. A generic action detector sees "stirring pot" but a cook knows the difference between adding salt, adding garam masala, and adding turmeric.

This system bridges that gap — when the initial detection misses the specifics, we progressively zoom in until we find what the user actually means, or honestly admit we can't.

## Related Files

- Backend refine handler: `backend/app/routers/edit_plan.py` (line ~679)
- Refine system prompt: same file (line ~33)
- Refine tool schema: same file (line ~98)
- Frontend proposal UI: `frontend/app/dashboard/project/[id]/page.tsx` (line ~960)
- Action detection: `backend/app/services/action_detection.py`
- Frame extraction: `backend/app/services/frame_extraction.py`
- Project doc: `videopeen/PROJECT.md`
