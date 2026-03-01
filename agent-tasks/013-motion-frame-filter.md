# Task 013: Motion-Based Frame Filtering

## Goal
Replace blind "1 frame every 2 seconds" extraction with smart motion-based filtering. Extract frames densely (1fps), then filter out redundant frames where nothing visually changed. Target: 50-70% fewer frames sent to Claude API = 50-70% cost reduction on action detection.

## Current System
- File: `backend/app/services/video_processor.py`
- `extract_dense_frames()` extracts 1 frame every 2s using ffmpeg `fps` filter
- Returns `DenseFrameResult` with `frame_paths` and `frame_timestamps`
- Called from `backend/app/services/pipeline.py` in `run_pipeline()`
- Downstream: `detect_actions_for_video()` in `video_analyzer.py` receives these frames

## Implementation Plan

### Step 1: Add motion filtering function to `video_processor.py`

Create a new function `filter_frames_by_motion()` that:

```python
def filter_frames_by_motion(
    frame_paths: list[str],
    frame_timestamps: list[float],
    diff_threshold: float = 0.03,      # 3% pixel difference = "changed"
    min_interval: float = 2.0,          # Never skip more than this many seconds
    max_interval: float = 10.0,         # Always keep at least 1 frame per this many seconds
    always_keep_first_last: bool = True, # Always keep first and last frames
) -> tuple[list[str], list[float]]:
    """Filter extracted frames, keeping only those with significant visual change.
    
    Algorithm:
    1. Compare each frame to the last KEPT frame using structural similarity
    2. If difference > threshold → KEEP (something changed)
    3. If time since last kept frame > max_interval → KEEP (safety net)
    4. If difference < threshold AND time < max_interval → SKIP (redundant)
    5. Always keep first and last frames
    
    Returns filtered (frame_paths, frame_timestamps)
    """
```

**Use OpenCV** for frame comparison:
- `cv2.imread()` to load frames
- Resize to small (160x120) for fast comparison
- `cv2.absdiff()` for pixel difference
- Normalize: `diff_score = np.mean(diff) / 255.0` (0.0 = identical, 1.0 = completely different)
- threshold of 0.03-0.05 works well (experiment)

**Alternative (simpler, no OpenCV dependency):** Use perceptual hash (imagehash library):
- `imagehash.phash(PIL.Image.open(path))` 
- Compare hashes: `hash1 - hash2` gives hamming distance
- Distance > 8 = visually different enough to keep

**Recommendation:** Use OpenCV since it's more standard and gives a continuous score. Add `opencv-python-headless` to requirements.txt.

### Step 2: Modify `extract_dense_frames()` 

Change frame extraction to 1fps (denser initial extraction):
```python
# Change fps from 0.5 (1 every 2s) to 1.0 (1 every 1s)
fps_value = 1.0  # Extract at 1fps for motion analysis
```

Then after extraction, apply motion filter:
```python
# Filter redundant frames
filtered_paths, filtered_timestamps = filter_frames_by_motion(
    frame_paths, frame_timestamps,
    diff_threshold=0.03,
    min_interval=2.0,
    max_interval=8.0,
)
logger.info("Motion filter: %d → %d frames (%.0f%% reduction)",
            len(frame_paths), len(filtered_paths),
            (1 - len(filtered_paths)/len(frame_paths)) * 100)
```

Return the filtered results in `DenseFrameResult`.

### Step 3: Update DenseFrameResult

Add stats fields:
```python
@dataclass
class DenseFrameResult:
    video_path: str
    total_duration: float
    frame_paths: list[str] = field(default_factory=list)
    frame_timestamps: list[float] = field(default_factory=list)
    frame_interval: float = 1.0  # Changed from 2.0
    total_extracted: int = 0     # NEW: before filtering
    total_filtered: int = 0      # NEW: after filtering
```

### Step 4: Add opencv-python-headless to requirements

```
# In backend/requirements.txt, add:
opencv-python-headless>=4.8.0
```

Then install: `cd backend && source .venv/bin/activate && pip install opencv-python-headless`

## Important Notes

- Do NOT change the pipeline.py or video_analyzer.py files - they just receive frame_paths/timestamps and don't care how they were selected
- The motion filter is purely in video_processor.py
- Keep the old frame_interval parameter working (backwards compat)
- Add a `motion_filter: bool = True` parameter to `extract_dense_frames()` so it can be disabled
- Log the filtering stats clearly so we can tune thresholds
- Delete filtered-out frame files from disk to save space (they're just JPEGs in the frames dir)

## Testing

After implementation:
1. `cd backend && source .venv/bin/activate && pip install opencv-python-headless`
2. Write a quick test script `backend/test_motion_filter.py`:
```python
"""Test motion filter on existing extracted frames."""
import sys
sys.path.insert(0, '.')
from app.services.video_processor import filter_frames_by_motion
import glob

# Use existing frames from a project
frames_dir = "./uploads/<project_id>/frames/"
frames = sorted(glob.glob(f"{frames_dir}/*.jpg"))
timestamps = [i * 1.0 for i in range(len(frames))]  # fake 1fps timestamps

filtered_paths, filtered_ts = filter_frames_by_motion(frames, timestamps)
print(f"Before: {len(frames)} frames")
print(f"After: {len(filtered_paths)} frames")
print(f"Reduction: {(1 - len(filtered_paths)/len(frames)) * 100:.0f}%")
```
3. Run: `python test_motion_filter.py`
4. Verify 40-70% reduction on real cooking footage

## Commit
After implementation + test: `git add -A && git commit -m "feat: motion-based frame filtering for 50-70% API cost reduction"`

## Environment
- Project root: `~/.openclaw/workspace/videopeen/`
- Backend venv: `backend/.venv/`
- Do NOT restart servers
- Existing project frames available at `backend/uploads/*/frames/` for testing
