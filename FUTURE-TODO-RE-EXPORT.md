# Future TODO: Re-Export in Different Format

**Status:** UI placeholder exists, backend NOT implemented  
**Effort:** 2-3 hours  
**Priority:** LOW (nice-to-have, not blocker)

---

## What's Missing

Users can't currently re-export a completed project in a different aspect ratio.

**Example use case:**
1. User creates project as 9:16 for TikTok
2. Wants to also post to YouTube (needs 16:9)
3. Should be able to click "Export as 16:9" → get new video

---

## Implementation Plan

### 1. Add Re-Export Endpoint

**File:** `backend/app/routers/projects.py`

```python
@router.post("/{project_id}/re-export")
async def re_export_with_aspect_ratio(
    project_id: str,
    aspect_ratio: str,  # "16:9", "9:16", "1:1"
    request: Request
):
    """Re-render the project with a different aspect ratio."""
    db = _db(request)
    
    # Validate aspect_ratio
    if aspect_ratio not in ("16:9", "9:16", "1:1"):
        raise HTTPException(400, "Invalid aspect ratio")
    
    # Get project
    project = await db.projects.find_one({"_id": project_id})
    if not project:
        raise HTTPException(404, "Project not found")
    
    # Update project aspect_ratio
    await db.projects.update_one(
        {"_id": project_id},
        {"$set": {"aspect_ratio": aspect_ratio}}
    )
    
    # Trigger re-render
    asyncio.create_task(render_from_edit_plan(db, project_id))
    
    return {
        "message": "Re-export started",
        "aspect_ratio": aspect_ratio,
        "status": "rendering"
    }
```

### 2. Handle Proxy Re-rendering

**Problem:** Existing proxies have old aspect_ratio

**Solution:** Add aspect_ratio check to `identify_new_clips()`

**File:** `backend/app/services/proxy_renderer.py`

```python
def identify_new_clips(
    new_timeline: list[dict[str, Any]],
    existing_proxy_map: dict[str, str],
    aspect_ratio: str = "16:9",  # NEW PARAM
) -> list[dict[str, Any]]:
    """Identify clips that need new proxy rendering.
    
    Returns list of clips that don't have existing proxies, 
    have changed speed_factor, OR have different aspect_ratio.
    """
    new_clips = []
    
    for clip in new_timeline:
        clip_id = clip.get("clip_id")
        speed_factor = clip.get("speed_factor", 1.0)
        
        if not clip_id:
            continue
        
        # Check if proxy exists
        if clip_id not in existing_proxy_map:
            new_clips.append(clip)
            continue
        
        proxy_path = existing_proxy_map.get(clip_id, "")
        proxy_filename = os.path.basename(proxy_path)
        
        # Check if speed_factor has changed (existing logic)
        if f"_s{speed_factor:.1f}" not in proxy_filename and speed_factor != 1.0:
            new_clips.append(clip)
            continue
        
        # NEW: Check if aspect_ratio has changed
        # Proxy filename could encode aspect ratio: {clip_id}_{aspect_ratio}_s{speed}.mp4
        # For now, if project aspect_ratio changed, re-render ALL proxies
        # (More efficient: encode aspect_ratio in proxy filename)
        
    return new_clips
```

**Better approach:** Encode aspect_ratio in proxy filename

```python
# In pre_render_proxy_clips():
if speed_factor != 1.0:
    output_path = os.path.join(proxies_dir, f"{clip_id}_{aspect_ratio}_s{speed_factor:.1f}.mp4")
else:
    output_path = os.path.join(proxies_dir, f"{clip_id}_{aspect_ratio}.mp4")
```

Then `identify_new_clips()` can check if proxy has correct aspect_ratio.

### 3. Update Frontend

**File:** `frontend/app/dashboard/project/[id]/page.tsx`

```typescript
const handleReExport = async (newFormat: string) => {
  if (!project || newFormat === project.aspect_ratio) return;
  
  try {
    const result = await api.reExportProject(id, newFormat);
    setHdRendering(true);
    toast("info", `Re-exporting as ${newFormat}...`);
    // WebSocket will update when complete
  } catch (e) {
    toast("error", "Re-export failed");
  }
};

// Update button
<button
  onClick={() => handleReExport(format.value)}
  disabled={hdRendering || format.value === project?.aspect_ratio}
>
  Export as {format.label}
</button>
```

**Add to API:**

```typescript
// frontend/lib/api.ts
reExportProject: (projectId: string, aspectRatio: string) =>
  apiFetch<any>(`/api/projects/${projectId}/re-export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ aspect_ratio: aspectRatio }),
  }),
```

### 4. Output File Naming

**Problem:** Multiple exports from same project → need different filenames

**Solution:** Include aspect_ratio in output filename

```python
# In render.py and pipeline.py:
output_filename = f"{project_id}_{aspect_ratio.replace(':', 'x')}_final.mp4"
# Examples:
# project_123_16x9_final.mp4
# project_123_9x16_final.mp4
# project_123_1x1_final.mp4
```

Store all outputs in project:
```python
# Project model:
output_paths: dict[str, str] = {}  # {"16:9": "path1", "9:16": "path2"}
```

---

## Testing Checklist

When implementing:

- [ ] Re-export changes aspect_ratio in DB
- [ ] Proxies re-render with new aspect_ratio
- [ ] HD render produces correct dimensions
- [ ] Multiple exports don't overwrite each other
- [ ] UI shows all available exports
- [ ] Download button works for each format
- [ ] WebSocket updates status correctly

---

## Effort Estimate

- Backend endpoint: 30 mins
- Proxy re-rendering logic: 1 hour
- Frontend integration: 30 mins
- Testing: 1 hour
- **Total: 2-3 hours**

---

## Alternative: Multi-Export at Creation

**Simpler approach:**

Instead of re-export, generate all 3 formats upfront:

```python
# In pipeline.py, after rendering:
for aspect_ratio in ["16:9", "9:16", "1:1"]:
    output_path = os.path.join(settings.output_dir, f"{project_id}_{aspect_ratio.replace(':', 'x')}_final.mp4")
    await asyncio.to_thread(stitch_clips_v2, stitch_entries, output_path, aspect_ratio)
```

**Pros:**
- No re-rendering needed
- All formats ready instantly

**Cons:**
- 3x render time (15 mins → 45 mins)
- 3x storage space
- Might not need all formats

**Verdict:** Re-export on demand is better UX
