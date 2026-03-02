# Task 016: Smart Clip Finding — Layer 3 (Targeted Re-Scan)

## Context
Read `videopeen/docs/SMART-CLIP-FINDING.md` for full design.
Read `backend/app/services/clip_finder.py` for existing Layers 0, 2, 5.

## What to Build

### Layer 3A: Gap Scanning
Scan time ranges BETWEEN existing detected actions where no clip was extracted.

Add to `backend/app/services/clip_finder.py`:

```python
async def scan_gaps(
    query: str,
    all_clips: list[dict],
    project_id: str,
    min_gap_seconds: float = 1.0,
) -> list[dict]:
    """Layer 3A: Find and scan gaps between detected clips.
    
    1. Sort clips by start_time per source video
    2. Find gaps > min_gap_seconds between clip end and next clip start
    3. Also check gap before first clip and after last clip (up to video duration)
    4. Extract frames from gaps
    5. Send to vision model with focused query
    6. Return any new clip entries found
    """
```

### Layer 3B: Generic Clip Re-Scanning
Scan clips that have vague/generic descriptions.

```python
GENERIC_KEYWORDS = [
    "stirring", "cooking", "preparing", "handling", "mixing",
    "working", "moving", "adjusting", "holding", "standing",
    "general", "overhead", "wide shot", "kitchen"
]

async def scan_generic_clips(
    query: str,
    all_clips: list[dict],
    project_id: str,
    max_clips: int = 10,
) -> list[dict]:
    """Layer 3B: Re-scan clips with generic descriptions using focused vision.
    
    1. Filter clips whose descriptions contain generic keywords
    2. Extract 5 frames per clip (more than Layer 2 for better coverage)
    3. Vision prompt specifically looking for the user's query
    4. Return clips where the query content is found
    """
```

### Combined Layer 3

```python
async def targeted_rescan(
    query: str,
    all_clips: list[dict],
    project_id: str,
) -> list[dict]:
    """Layer 3: Combined gap scan + generic clip re-scan.
    
    Runs 3A and 3B concurrently, merges results.
    """
```

### Video Duration Discovery
Need to know total video duration to find gaps at start/end. Add helper:

```python
async def _get_video_duration(video_path: str) -> float:
    """Get video duration in seconds using ffprobe."""
```

### New Clip Creation
When Layer 3 finds content in a gap or within a generic clip, create a new clip dict:

```python
def _create_discovered_clip(
    source_video: str,
    start_time: float,
    end_time: float,
    description: str,
    visual_quality: int = 5,
) -> dict:
    """Create a new clip dict for a discovered moment."""
```

The clip should have a unique `clip_id` (uuid4), and be marked with `"discovered": True` so we know it wasn't from the original detection.

### Update orchestrator
Update `smart_find_clip()`: Layer 0 → Layer 2 → Layer 3 → Layer 5

## Files to Modify
- MODIFY: `backend/app/services/clip_finder.py`

## Constraints
- Use claude-haiku-3-5 for vision calls
- Run 3A and 3B concurrently (asyncio.gather)
- Max 20 frames per API call to keep costs reasonable
- If a source video file doesn't exist, skip it gracefully
- Total Layer 3 timeout: 60 seconds
- Log clearly what gaps/clips are being scanned
