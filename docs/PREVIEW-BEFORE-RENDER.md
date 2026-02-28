# Videopeen: "Preview Before Render" — Production Blueprint

> Generated: Feb 22, 2026 | Status: Planning

## Overview

### New Flow
```
Upload → AI Analyze → REVIEW SCREEN (new!) → User edits → Confirm → Render → Done
```

Instead of auto-stitching after AI analysis, we show the user the proposed edit plan as visual clip cards. User reviews, reorders, removes, adds clips. Only after confirmation do we render the final video.

### Why
- No more wasted 15-min renders on wrong clip ordering
- User has full control before committing to render
- Re-stitch after changes takes 2-3 seconds (not 15 min)

---

## 1. Data Model (MongoDB)

### `editPlans` Collection

```javascript
{
  _id: ObjectId,
  projectId: ObjectId,
  userId: ObjectId,
  status: "draft" | "confirmed" | "rendering" | "completed" | "failed",
  
  // Version tracking (undo/redo)
  version: 3,
  history: [
    {
      version: 1,
      source: "ai",           // "ai" | "user"
      action: "initial_generation",
      timestamp: ISODate,
      snapshot: "<full timeline state>"
    },
    {
      version: 2,
      source: "user",
      action: "reorder",
      detail: { clipId: "c3", fromIndex: 4, toIndex: 1 },
      timestamp: ISODate,
      snapshot: "..."
    }
  ],
  currentVersionPointer: 3,   // for undo/redo navigation
  
  // Current timeline state
  timeline: {
    totalDuration: 185.4,     // seconds, computed
    clips: [
      {
        clipId: "clip_a1b2c3",
        sourceFileId: ObjectId,
        inPoint: 12.300,                // seconds into source
        outPoint: 28.750,
        duration: 16.45,                // computed
        order: 0,
        
        // AI metadata
        ai: {
          label: "Chopping onions",
          category: "prep" | "cooking" | "plating" | "intro" | "outro",
          confidence: 0.92,
          detectedActions: ["chopping", "knife_work"],
          sceneQuality: 0.85,
          suggestedTransition: "crossfade",
          reasoning: "Clear overhead shot of knife technique"
        },
        
        // User overrides (null = unchanged from AI)
        overrides: {
          label: null,
          inPoint: 13.0,
          outPoint: null,
          transition: "cut"
        },
        
        // State
        status: "included",            // "included" | "excluded" | "added_by_user"
        addedBy: "ai",                 // "ai" | "user"
        thumbnailUrl: "https://...",
        waveformData: [...]
      }
    ]
  },
  
  // Pool of ALL detected clips (superset of timeline)
  clipPool: [
    {
      clipId: "clip_x9y8z7",
      sourceFileId: ObjectId,
      inPoint: 55.0,
      outPoint: 61.2,
      ai: { label: "Blurry transition", confidence: 0.3, sceneQuality: 0.2 },
      rejectionReason: "low_quality",
      status: "excluded"
    }
  ],
  
  aiModel: { name: "videopeen-v6", runId: "run_abc123" },
  createdAt: ISODate,
  updatedAt: ISODate
}
```

### Key Design Decisions
- **Undo/Redo**: Each edit appends to `history` with full snapshot. `currentVersionPointer` tracks position — undo decrements, redo increments. Snapshots beyond pointer get pruned on new edits (fork behavior).
- **AI vs User tracking**: `addedBy` marks origin. `overrides` keeps user changes separate from AI values — can always diff or revert per-field.
- **Excluded clips**: `clipPool` holds everything AI detected. `timeline.clips` is the active edit. Users drag from pool → timeline.
- **Indexes**: `{ projectId, userId }`, `{ status }`, `{ "timeline.clips.clipId": 1 }`

---

## 2. UI/UX Design — Review & Arrange Screen

### Layout (Desktop)
Full-screen dark canvas (`#0D0D0F`). Three zones:

**Top Bar**
- Project name (editable inline)
- Total duration badge (`1:02`)
- Undo/redo arrows
- "Preview" button (ghost, orange border)
- "Render Final" button (solid orange `#FF6B2C`, pill-shaped, right-aligned)

**Main Timeline (center, 65% height)**
- Horizontal scrollable strip of clip cards
- Cards snap to grid with 8px gaps
- Drop zones glow orange on drag-hover
- Thin orange progress line spans bottom showing total video duration with tick marks

**Unused Clips Drawer (bottom, 30% height)**
- Collapsible panel with header: "Available Clips (7)" + chevron toggle
- Grid layout (3-4 columns)
- Clips here are slightly desaturated
- Drag up to add to timeline; drag down from timeline to remove

### Clip Card Design
**Size:** 180×120px (timeline), 140×96px (drawer)

Each card shows:
- **Thumbnail** — keyframe with 2px rounded corners, subtle hover zoom (1.03×)
- **Duration pill** — bottom-right overlay, `0:14`, semi-transparent black bg
- **Action label** — bottom-left, bold 11px, e.g. "Searing the steak"
- **Cooking stage badge** — top-left colored dot + label: 🔵 Prep / 🟠 Cook / 🟢 Plating / 🟡 Serve
- **Drag handle** — 6-dot grip icon, top-right, visible on hover
- **Remove button** — `×` icon, top-right on hover (timeline cards only)
- **AI confidence dot** — green/yellow/red in corner, tooltip shows reasoning

**Selected state:** orange border 2px
**Dragging state:** slight rotation (2°), elevated shadow, 80% opacity at origin

### Micro-interactions
- Card entry: staggered fade-up (50ms delay each)
- Reorder: 200ms spring ease
- Remove: card shrinks + fades, siblings slide in
- Render button: subtle pulse animation when arrangement differs from AI default

### Mobile (< 768px)
- Timeline becomes vertical stack (full-width cards, 100×80px thumbnails)
- Unused clips in bottom sheet (swipe up)
- Long-press to drag
- "Render Final" becomes sticky bottom CTA bar

---

## 3. Preview System

### Thumbnail Pipeline
- **Reuse existing frames** from the pipeline (already extracting every 2s for AI analysis)
- Pick frame at clip's **33% mark** (not midpoint — cooking clips have action in first third)
- If AI scene-quality scores available, prefer highest visual complexity frame
- **Format:** WebP, 320×180, quality 75, ~8-15KB per thumbnail
- **Storage:** Individual images (not sprite sheets — clips get reordered/deleted)
- **Serving:** S3/R2 → CDN, immutable cache 1 year
- First 3 thumbnails inline as base64 in API response for instant render
- Blurhash placeholder (4×3, ~20 bytes) per clip for loading state

### Individual Clip Preview
- Click clip card → inline `<video>` plays that segment via `#t=start,end` media fragment
- No custom player needed for single clip preview

### Full Sequence Preview
- **Double-buffer technique:** Two `<video>` elements, alternating
- While clip A plays, clip B preloads next segment
- On clip A near end, crossfade to B
- Works with any browser-playable format (no MSE needed)
- **Fallback:** If codec not browser-playable (HEVC on Firefox), serve 720p H.264 proxy

### Timeline Scrubbing
- `<canvas>`-drawn timeline bar with sprite thumbnails
- Hover/drag: render corresponding frame to tooltip
- Click: seek relevant `<video>` element
- `requestAnimationFrame` loop syncs playhead to `video.currentTime`
- Progress fills proportionally across all clips

### Mobile Preview
- Horizontal card scroll with snap points (`scroll-snap-type`)
- Tap-to-play replaces hover
- Fullscreen playback via native `<video>` controls with `playsinline`

---

## 4. Clip Library (Unused Clips)

### Data
Every detected action gets a `ClipAction` record regardless of AI selection:
```
ClipAction {
  id, sourceTimestamp, duration,
  stage: prep | cook | plate | other,
  label: "dicing onions",
  qualityScore: 0-100,
  aiSelected: boolean,
  thumbnailUrl, previewUrl,
  tags: ["close-up", "hands", "plating"]
}
```

### UI: Collapsible Right Panel / Bottom Drawer
- **Top bar:** Search field + filter chips: `Stage` (prep/cook/plate) · `Quality` (★★★+) · `Not in edit` toggle
- **Body:** Thumbnail grid (3-col, 120px cards)
- Cards grouped by stage with sticky headers: `🥕 Prep → 🔥 Cook → 🍽 Plate`
- **Hover:** Scrubable thumbnail (mousemove across card = scrub through clip)
- **Click:** Inline expanded preview with full metadata

### Insertion Methods
1. **Drag & drop** — Drag card directly onto timeline, drop zone highlights valid insertion points
2. **Insert button** — Click "Insert" from preview, pick position from dropdown
3. **Right-click** — "Insert after current playhead," "Insert at end," "Replace selected clip"

On insert: clip moves from pool to timeline visually (blue checkmark), edit plan updates, fully undoable.

### Search
Client-side fuzzy match on label + tags (dataset small enough, no server search needed)

---

## 5. Drag & Drop System

### Library: `@dnd-kit/core` + `@dnd-kit/sortable`
- Tree-shakeable (~12KB), built-in keyboard/screen-reader support
- First-class touch sensors, composition-based architecture

### Architecture
```
ClipTimeline (DndContext + SortableContext)
├── SortableClip[] (useSortable hook per clip)
│   ├── ClipThumbnail
│   ├── DragHandle
│   └── DurationBadge
└── DragOverlay (portal-rendered ghost)
```

### State Management
- **Zustand** store holds `clipIds: string[]`
- On `onDragEnd`, dispatch `reorderClips(activeId, overId)` → `arrayMove()`
- **Undo/redo**: `zundo` middleware for Zustand, `Cmd+Z` / `Cmd+Shift+Z` bound globally

### Sensors
```typescript
const sensors = useSensors(
  useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  useSensor(TouchSensor, { activationConstraint: { delay: 150, tolerance: 5 } }),
  useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
);
```

### Performance (20-30 clips)
- Each `SortableClip` wrapped in `React.memo`
- Thumbnails lazy-loaded via `IntersectionObserver`
- `clipIds` array is minimal reactive state
- Optimistic UI: reorder is local-first, debounced save (500ms) PATCHes backend

### Accessibility
- Live `aria-describedby` announcements: "Moved 'Dice Onions' to position 4"
- Full keyboard navigation

---

## 6. Backend Architecture

### API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/projects/:id/edit-plan` | Get current edit plan + clip pool |
| `PATCH` | `/projects/:id/edit-plan` | Save reorder/add/remove (accepts full clips array) |
| `POST` | `/projects/:id/edit-plan/confirm` | Lock plan, enqueue render |
| `GET` | `/clips/:id/thumbnail` | Serve thumbnail (lazy gen, cached) |
| `GET` | `/clips/:id/preview` | Stream low-res clip segment |
| `WS` | `/projects/:id/render/progress` | Real-time render progress |

### Clip Storage: On-Demand with Cache
Don't pre-cut clips. Store only timestamps. Generate thumbnails/previews on first request, cache:
```python
async def get_thumbnail(clip):
    cache_key = f"thumb/{clip.clip_id}.jpg"
    if not await storage.exists(cache_key):
        await ffmpeg_extract_frame(clip.source_file, midpoint, cache_key)
    return cache_key
```

### State Enforcement
- All state transitions validated server-side
- `PATCH` rejects if status ≠ `draft`
- `confirm` sets status atomically with version check (prevent double-submit)
- Concurrent tabs: optimistic locking via `version` field, `409 Conflict` on mismatch

---

## 7. Render Pipeline

### Step 1: Normalize (parallel, per-clip, one-time)
```bash
ffmpeg -i clip_N.mov \
  -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:-1:-1,fps=30" \
  -c:v libx264 -profile:v high -crf 18 -preset fast \
  -g 30 -keyint_min 30 \
  -c:a aac -ar 48000 -ac 2 -b:a 192k \
  -movflags +faststart -y normalized/clip_N.mp4
```
Fixed GOP ensures every clip starts/ends on keyframe. Uniform params eliminate concat issues.

### Step 2a: No Transitions (fast path, 2-3 seconds)
```bash
# filelist.txt from edit plan JSON
file 'normalized/clip_0.mp4'
file 'normalized/clip_1.mp4'

ffmpeg -f concat -safe 0 -i filelist.txt -c copy -movflags +faststart output.mp4
```
Zero re-encoding!

### Step 2b: With Crossfades (full re-encode)
```bash
ffmpeg -i clip_0.mp4 -i clip_1.mp4 -i clip_2.mp4 \
  -filter_complex "
    [0:v][1:v]xfade=transition=fade:duration=0.5:offset=4.5[v01];
    [v01][2:v]xfade=transition=fade:duration=0.5:offset=9.0[vout];
    [0:a][1:a]acrossfade=d=0.5[a01];
    [a01][2:a]acrossfade=d=0.5[aout]" \
  -map "[vout]" -map "[aout]" \
  -c:v libx264 -crf 23 -preset medium \
  -movflags +faststart output.mp4
```

### Quality Presets

| Preset | CRF | Preset | Resolution |
|--------|-----|--------|------------|
| draft  | 28  | ultrafast | 720p |
| standard | 23 | medium | 1080p |
| high   | 18  | slow   | 1080p |

### Progress Reporting
```bash
ffmpeg ... -progress pipe:1
```
Parse `out_time_us`, divide by total expected duration → percentage → WebSocket

### Error Recovery
- Normalize jobs are idempotent — retry up to 3x
- On render fail: normalized clips still cached, retry render only
- OOM/timeout: fall back to `draft` preset, notify user

---

## 8. Smart Features

### Color-Coded Cooking Stages
Four-color system: 🔵 prep, 🟠 cook, 🟢 plate, 🟡 serve. Each clip card shows its stage color. Instant visual flow comprehension.

### Sequence Validator
Passive rule engine checks cooking logic in real-time:
- Plating before cooking? → amber warning bar with "Fix" button
- Non-blocking inline banners, never modals

### Coverage Map
Collapsible sidebar listing every recipe step:
- ✅ Covered steps (checkmark)
- 🔴 Missing steps (pulse): "Missing: season the steak, rest before slicing"
- Each missing step offers "Find Clip" (search raw footage) or "Mark Optional"

### Duration Gauge
Bar beneath timeline: current total vs target duration, segmented by stage color. Live updates on edit.

### Duplicate Detection
Two clips showing same action → dotted connector + "possible duplicate" label. One click keeps better-scored clip.

### Suggested Reorder
Single button proposes optimized sequence based on recipe logic + pacing. Ghost overlay preview — accept, reject, or cherry-pick individual moves.

---

## 9. State Machine

### States & Transitions
```
IDLE → UPLOADING → ANALYZING → REVIEW → EDITING → RENDERING → COMPLETED
                                                        ↓
                                           EDITING ← ERROR (retry)
                                           EDITING ← COMPLETED (re-edit)
```

| State | UI | WebSocket Events |
|---|---|---|
| `IDLE` | Upload dropzone | — |
| `UPLOADING` | Progress bar | `upload:progress` |
| `ANALYZING` | Skeleton + phase text | `analyze:phase`, `analyze:progress` |
| `REVIEW` | Timeline with AI-proposed clips (read-only preview) | `review:ready` |
| `EDITING` | Full drag/reorder/remove/add editor | `edit:autosave` |
| `RENDERING` | Progress bar + ETA, locked timeline | `render:progress` |
| `COMPLETED` | Video player + Download/Share | `render:done` |
| `ERROR` | Error banner with retry | `error` |

### Auto-Save
- EDITING state: debounced autosave every 5s
- Each save bumps `version` counter
- On reconnect: fetch project → hydrate into correct state

### Edge Cases
- **Leave mid-upload:** Resumable uploads. Returns to same byte offset.
- **Leave mid-analysis:** Server continues. Returns to REVIEW if done, ANALYZING if not.
- **Render fails:** → ERROR with fallback to EDITING. User edits and re-queues.
- **Re-edit after complete:** COMPLETED → EDITING clones edit plan. Original render preserved.
- **Concurrent tabs:** Optimistic locking via `version`. Second tab gets `409 Conflict`.
- **WebSocket disconnect mid-render:** Client polls status as fallback (30s interval).

---

## 10. Implementation Priority

### Phase 1 (Week 1-2): Core Review Screen
1. Modify pipeline to stop after edit plan (don't auto-stitch)
2. Store edit plan + clip pool in MongoDB
3. Thumbnail generation (reuse existing frames)
4. Review screen UI with clip cards
5. Drag-drop reorder (@dnd-kit)
6. Remove clip
7. Confirm + render endpoint

### Phase 2 (Week 3): Preview + Polish
1. Click-to-preview individual clips
2. Full sequence preview (double-buffer)
3. Unused clips drawer
4. Undo/redo
5. Auto-save

### Phase 3 (Week 4): Smart Features
1. Color-coded cooking stages
2. Duration gauge
3. Sequence validator
4. Coverage map
5. Suggested reorder

### Phase 4 (Future)
1. Trim/speed per clip
2. Crossfade transitions
3. Auto-captions
4. Multi-format export
5. Text overlays
6. Music
7. Direct publish to TikTok/Instagram
