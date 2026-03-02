# Task 020: 2fps Extraction + SSIM Scene Selection (Replacing Motion Filter)

## Context
Read `videopeen/docs/ACTION-DETECTION-FIX.md` for full design context.
Read `backend/app/services/video_processor.py` — this is the main file you'll modify.

## What to Build

### Overview
Replace the current "1fps extraction + motion filter" with "2fps extraction + SSIM-based scene selection." The motion filter drops brief actions. SSIM scene selection KEEPS brief actions.

### 1. New function: SSIM-based frame selection

Add a new function (can be in video_processor.py or a new file `backend/app/services/scene_selector.py`):

```python
from skimage.metrics import structural_similarity as ssim
# OR use opencv if skimage not available

def select_frames_by_scene(
    frame_paths: list[str],
    frame_timestamps: list[float],
    ssim_threshold: float = 0.90,
) -> tuple[list[str], list[float]]:
    """Select frames using SSIM-based scene segmentation.
    
    Key rule: brief scenes (<2s) keep ALL frames.
    This inverts the motion filter's behavior where brief actions get dropped.
    
    Args:
        frame_paths: All extracted frame paths
        frame_timestamps: Corresponding timestamps
        ssim_threshold: Scene break threshold (adaptive per video)
    
    Returns:
        (selected_paths, selected_timestamps)
    """
```

Implementation:
1. Downsample all frames to 256x256 for fast SSIM computation
2. Compute pairwise SSIM between consecutive frames
3. Compute adaptive threshold: `max(0.85, median(all_ssim) - 0.05)`
4. Use two-signal gate for scene breaks:
   ```python
   def is_scene_break(prev, curr, threshold):
       full_ssim = compute_ssim(prev, curr)  # full 256x256
       if full_ssim > threshold:
           return False   # clearly same scene
       if full_ssim < threshold - 0.10:
           return True    # clearly different scene
       # Ambiguous: check center crop (wobble affects edges, not center)
       center_ssim = compute_ssim_center_crop(prev, curr, crop_ratio=0.5)
       return center_ssim < threshold
   ```
5. Segment frames into scenes based on breaks
6. Per-scene frame selection:
   - Scene < 2.0s: **KEEP ALL FRAMES** (brief action!)
   - Scene 2.0-5.0s: keep first, middle, last
   - Scene > 5.0s: keep first + last + 1 per 4s interior
7. ALWAYS keep both frames at every scene boundary transition
8. Log: number of scenes, frames kept, compression ratio

### 2. Modify extract_dense_frames

Change the default `frame_interval` from 2.0 to 0.5 (= 2fps).

Replace the motion_filter call with the new SSIM selection:

```python
# OLD:
if motion_filter and total_extracted > 1:
    filtered_paths, filtered_timestamps = filter_frames_by_motion(...)

# NEW:
filtered_paths, filtered_timestamps = select_frames_by_scene(
    all_extracted_paths, all_extracted_timestamps
)
```

Keep the `motion_filter` parameter but deprecate it (log a warning if True, use SSIM regardless).

### 3. Dependencies
- Need `scikit-image` for SSIM, OR implement using OpenCV's `cv2.matchTemplate` / manual SSIM
- Check if scikit-image is already in requirements. If not, prefer OpenCV-based SSIM to avoid new deps
- `cv2` (opencv-python) should already be available
- `numpy` should already be available

### OpenCV SSIM implementation (if scikit-image not available):
```python
import cv2
import numpy as np

def compute_ssim_cv2(img1, img2):
    """Compute SSIM between two grayscale images using OpenCV."""
    C1 = (0.01 * 255) ** 2
    C2 = (0.03 * 255) ** 2
    
    img1 = img1.astype(np.float64)
    img2 = img2.astype(np.float64)
    
    mu1 = cv2.GaussianBlur(img1, (11, 11), 1.5)
    mu2 = cv2.GaussianBlur(img2, (11, 11), 1.5)
    
    mu1_sq = mu1 ** 2
    mu2_sq = mu2 ** 2
    mu1_mu2 = mu1 * mu2
    
    sigma1_sq = cv2.GaussianBlur(img1 ** 2, (11, 11), 1.5) - mu1_sq
    sigma2_sq = cv2.GaussianBlur(img2 ** 2, (11, 11), 1.5) - mu2_sq
    sigma12 = cv2.GaussianBlur(img1 * img2, (11, 11), 1.5) - mu1_mu2
    
    ssim_map = ((2 * mu1_mu2 + C1) * (2 * sigma12 + C2)) / \
               ((mu1_sq + mu2_sq + C1) * (sigma1_sq + sigma2_sq + C2))
    
    return float(np.mean(ssim_map))
```

### 4. Update DenseFrameResult
If needed, add a field to track scene info:
```python
scene_count: int = 0
frames_before_selection: int = 0
```

## Files to Create/Modify
- MODIFY: `backend/app/services/video_processor.py` (or CREATE `backend/app/services/scene_selector.py`)
- Do NOT modify video_analyzer.py or pipeline.py (they consume frame_paths/timestamps which stay the same interface)

## Testing
- Verify extract_dense_frames still returns (frame_paths, frame_timestamps) in the same format
- The pipeline.py caller should work unchanged

## Constraints
- Prefer OpenCV over scikit-image to avoid new dependencies
- Frame downsampling to 256x256 for SSIM (not full resolution)
- Total SSIM computation should take <10s for ~8000 frames
- Clean up: do NOT delete the old motion filter code yet, just don't call it by default
- Log clearly: "SSIM scene selection: X scenes detected, Y/Z frames kept (compression ratio)"

After implementation, git add, commit with message "feat: 2fps extraction + SSIM scene selection replacing motion filter" and push.
