# Task 022: Critical Pipeline Bug Fixes

**Priority:** CRITICAL
**Scope:** Backend only — `backend/app/services/`
**Goal:** Fix all bugs identified in the expert engineering review

---

## Bug 1: Last frame of video silently dropped

**File:** `backend/app/services/video_analyzer.py` → `detect_actions_for_video()`

**Problem:** Batch overlap math uses wrong end boundary. For a 30-frame video with batch_size=15:
- Batch 0: `[0, 15)` ✓
- Batch 1: `start_idx = 15 - 1 = 14`, `end_idx = min(14 + 15, 30) = 29` → processes frames `[14, 29)` = frames 14-28
- Frame 29 is NEVER processed

**Fix:** Change end_idx calculation to use original boundary:
```python
# BEFORE (buggy):
start_idx = i * batch_size
if i > 0:
    start_idx -= 1
end_idx = min(start_idx + batch_size, n_frames)

# AFTER (fixed):
start_idx = i * batch_size
if i > 0:
    start_idx -= 1
end_idx = min((i + 1) * batch_size, n_frames)
```

---

## Bug 2: Zero-duration fix creates asymmetric clips

**File:** `backend/app/services/video_analyzer.py` → `detect_actions_for_video()`

**Problem:** When `end <= start`, the fix uses original `start` for `end_time`:
```python
action["start_time"] = max(0, start - 1.0)
action["end_time"] = start + 1.0  # Uses original start, not adjusted start_time
```

**Fix:**
```python
if end <= start:
    mid = start
    action["start_time"] = max(0, mid - 1.0)
    action["end_time"] = mid + 1.0
    zero_dur_fixed += 1
```

---

## Bug 3: Frame collection loop breaks on first missing file

**File:** `backend/app/services/video_processor.py` → `extract_dense_frames()`

**Problem:** If ffmpeg skips a frame number (VFR content), the loop `break`s and all subsequent frames are lost.

**Fix:** Use consecutive miss counter:
```python
# BEFORE:
for i in range(1, n_frames + 10):
    path = os.path.join(output_dir, f"v{video_index:02d}_frame_{i:04d}.jpg")
    if os.path.exists(path):
        timestamp = (i - 1) / extraction_fps
        if timestamp <= duration + (1.0 / extraction_fps):
            frame_paths.append(path)
            frame_timestamps.append(timestamp)
    else:
        break

# AFTER:
consecutive_misses = 0
for i in range(1, n_frames + 20):
    path = os.path.join(output_dir, f"v{video_index:02d}_frame_{i:04d}.jpg")
    if os.path.exists(path):
        consecutive_misses = 0
        timestamp = (i - 1) / extraction_fps
        if timestamp <= duration + (1.0 / extraction_fps):
            frame_paths.append(path)
            frame_timestamps.append(timestamp)
    else:
        consecutive_misses += 1
        if consecutive_misses > 3:
            break
```

---

## Bug 4: `step` variable undefined when `interior_frames` is empty

**File:** `backend/app/services/video_processor.py` → `select_frames_by_scene()`

**Problem:** In the long scene branch, if `interior_frames` is empty, `step` is undefined but used in the debug log.

**Fix:** Move the debug log inside the `if interior_frames:` block, OR define `step = 1` before the block:
```python
# Add default before the if block:
step = 1
interior_frames = scene_frame_indices[1:-1]
if interior_frames:
    frames_per_4s = max(1, int(scene_duration / 4.0))
    step = max(1, len(interior_frames) // frames_per_4s)
    for i in range(0, len(interior_frames), step):
        selected_indices.add(valid_indices[interior_frames[i]])

logger.debug("Scene %d: long (%.1fs), keeping first + last + %d interior",
            scene_idx, scene_duration, len(interior_frames[::step]))
```

---

## Bug 5: MongoDB client created per API call (60+ connections per project)

**File:** `backend/app/services/video_analyzer.py` → `_get_user_api_key()` and `_resolve_api_key()`

**Problem:** Every `detect_actions_batch()` call does `await _resolve_api_key()` → creates a new MongoDB client, queries, closes. For 3 videos × 20 batches = 60 connections for the same key. Also no try/finally so connection leaks on error.

**Fix:** 
1. Add `api_key` parameter to `detect_actions_batch()`, `detect_actions_for_video()`, and `create_edit_plan()`
2. Resolve the key ONCE in `pipeline.py` at the start and pass it through
3. Keep `_resolve_api_key()` but only call it once:

In `pipeline.py`, after recipe context is built:
```python
# Resolve API key once for entire pipeline
from app.services.video_analyzer import _resolve_api_key
pipeline_api_key = await _resolve_api_key()
```

Then pass `api_key=pipeline_api_key` to all calls. Update function signatures:
- `detect_actions_for_video(..., api_key: str | None = None)`
- `detect_actions_batch(..., api_key: str | None = None)`
- `create_edit_plan(..., api_key: str | None = None)`

Inside each function, use passed key or fallback:
```python
key = api_key or await _resolve_api_key()
client = _get_async_client(key)
```

---

## Bug 6: JSON parse failure silently drops entire batch

**File:** `backend/app/services/video_analyzer.py` → `detect_actions_batch()`

**Problem:** If Claude returns malformed JSON, `_extract_batch_json()` returns `{"actions": [], "batch_summary": "parse_error"}`. No retry. Entire batch (7.5s of video) silently lost.

**Fix:** Add retry on parse failure:
```python
# In detect_actions_batch(), after getting response:
result = _extract_batch_json(text)

# Retry once if parse failed
if result.get("batch_summary") == "parse_error":
    logger.warning("Parse error on batch %d, retrying...", batch_index + 1)
    response = await client.messages.create(
        model=settings.vision_model,
        max_tokens=2000,
        system=TIMELINE_SYSTEM,
        messages=[{"role": "user", "content": content}],
    )
    text = response.content[0].text
    result = _extract_batch_json(text)
    if result.get("batch_summary") == "parse_error":
        logger.error("Parse error on retry for batch %d, giving up", batch_index + 1)
```

---

## Bug 7: No API retry on rate limits or server errors

**File:** `backend/app/services/video_analyzer.py`

**Problem:** No retry on 429 (rate limit) or 500 (server error). With 7 concurrent calls, rate limits are likely.

**Fix:** Add `tenacity` to requirements and create a retry wrapper:

First, add to `backend/requirements.txt`:
```
tenacity>=8.0.0
```

Then in `video_analyzer.py`, add a retry wrapper:
```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

async def _call_claude_with_retry(client, **kwargs):
    """Call Claude API with exponential backoff retry."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return await client.messages.create(**kwargs)
        except Exception as e:
            error_str = str(e)
            is_retryable = any(code in error_str for code in ["529", "529", "rate_limit", "overloaded"])
            if hasattr(e, 'status_code'):
                is_retryable = is_retryable or e.status_code in [429, 500, 502, 503, 529]
            
            if is_retryable and attempt < max_retries - 1:
                wait_time = (2 ** attempt) + (attempt * 0.5)  # 1s, 2.5s, 5s
                logger.warning("API call failed (attempt %d/%d), retrying in %.1fs: %s", 
                              attempt + 1, max_retries, wait_time, str(e)[:100])
                await asyncio.sleep(wait_time)
            else:
                raise
```

Then replace all `await client.messages.create(...)` calls with `await _call_claude_with_retry(client, ...)`.

---

## Bug 8: Bare `except:` clauses swallowing all exceptions

**File:** `backend/app/services/clip_finder.py` — multiple locations

**Problem:** Several bare `except:` or `except: pass` that swallow KeyboardInterrupt, SystemExit, etc.

**Fix:** Change all bare `except:` to `except Exception:` in clip_finder.py. Search for these patterns:
```python
# BAD:
except:
    pass

# GOOD:
except Exception:
    pass
```

---

## Bug 9: Inconsistent model strings hardcoded in clip_finder.py

**File:** `backend/app/services/clip_finder.py`

**Problem:** Three different hardcoded model strings:
- Layer 2: `"claude-haiku-3-5-20250219"`
- Layer 3: `"claude-3-5-haiku-20241022"` (different Haiku version!)
- Layer 4: `"claude-sonnet-4-5-20250514"`

**Fix:** 
1. Add `fast_vision_model` to config:
```python
# In config.py Settings class:
fast_vision_model: str = "claude-haiku-3-5-20250219"
```

2. Replace all hardcoded model strings in clip_finder.py:
- Layer 2 (`visual_recheck_clips`): `model=settings.fast_vision_model`
- Layer 3 (`_vision_scan_frames`): `model=settings.fast_vision_model`  
- Layer 4 (`full_redetect`): `model=settings.vision_model`

Import settings at top: `from app.config import settings`

---

## Bug 10: ffmpeg subprocess without timeout

**File:** `backend/app/services/video_processor.py` → `extract_dense_frames()`

**Problem:** `subprocess.run(cmd, capture_output=True, text=True)` has no timeout. Corrupted video = hang forever.

**Fix:**
```python
result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
```

Also in `get_video_duration()`:
```python
result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
```

---

## Testing

After implementing all fixes:
1. Verify the batch boundary fix by checking logs for total frames processed
2. Verify API retry by checking logs for "retrying" messages
3. Verify model strings are from config by checking startup logs
4. Run a full pipeline on a test video and compare output quality

---

## Files Modified
- `backend/app/services/video_analyzer.py` (Bugs 1, 2, 5, 6, 7)
- `backend/app/services/video_processor.py` (Bugs 3, 4, 10)
- `backend/app/services/clip_finder.py` (Bugs 8, 9)
- `backend/app/services/pipeline.py` (Bug 5 — pass api_key)
- `backend/app/config.py` (Bug 9 — add fast_vision_model)
- `backend/requirements.txt` (Bug 7 — add tenacity)

## DO NOT
- Do not modify frontend code
- Do not change the pipeline flow/architecture
- Do not restart servers (Haxx will do that)
