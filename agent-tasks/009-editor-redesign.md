# Task 009: Editor Redesign — Split Panel Workspace

**Priority:** HIGH
**Effort:** 1-2 weeks
**Depends on:** Task 007, Task 008

## Context
The editor is currently a scrollable page. Users can't see video preview and AI chat simultaneously. The #1 recommendation from UI review is a split-panel workspace layout.

## Target Layout
```
┌──────────────────────────────────────────────────────┐
│  ← Projects    Cooking Video - Feb 28    Save  Export │
├────────────────────────┬─────────────────────────────┤
│                        │  [Tab: AI Chat] [Tab: Manual]│
│    [Video Preview]     │                              │
│     9:16 / 1:1 / 16:9 │  AI: I created 18 clips...  │
│    ▶ ────●──── 0:54    │  You: Remove blurry ones     │
│                        │  AI: Done! Removed 3 clips   │
│    [Edit Summary Card] │                              │
│                        │  [Prompt chips]              │
│                        │  [Chat input] [Send]         │
├────────────────────────┴─────────────────────────────┤
│  [Clip Timeline — draggable thumbnails with tags]     │
│  🔪Clip1 🍳Clip2 ✨Clip3 ⚡Clip4 ... 🎬Clip18        │
│  Text Overlays: [+ Add] [✨ Auto-generate]            │
└──────────────────────────────────────────────────────┘
```

## Checklist

### 1. Split Panel Layout (2-3 days)
- [x] Replace single-column scrollable layout with CSS Grid or flexbox split panel
- [x] Left panel (55%): Video preview + export format + summary card
- [x] Right panel (45%): AI chat + manual arrange (tabbed)
- [x] Bottom strip: Clip timeline + text overlays
- [ ] Responsive: on mobile, stack panels vertically (TODO: add mobile breakpoints)
- [x] No page scrolling — everything fits in viewport (overflow within panels)

### 2. Persistent Video Preview (1 day)
- [x] Video player always visible in left panel
- [x] HTML5 video controls (play/pause, scrub, timestamp, volume, fullscreen)
- [ ] Spacebar = play/pause shortcut (TODO: add keyboard handler)
- [x] Format toggle (9:16/1:1/16:9) below video (displays current format)

### 3. Tabbed Right Panel (2-3 days)
- [x] Tab 1: AI Chat — conversational editing with history, prompt chips, undo/redo
- [x] Tab 2: Manual Arrange — clip cards with drag/reorder, delete controls
- [x] Smooth tab switching, preserves state
- [x] Merged Review & Arrange page functionality into Tab 2

### 4. Draggable Clip Timeline (3-5 days)
- [x] Bottom strip with real thumbnail frames
- [x] Drag to reorder clips (in Manual tab grid view)
- [ ] Click to jump video to that clip (TODO: add video seek on click)
- [ ] Highlight currently playing clip (TODO: track current time)
- [x] Delete (x) button on clip cards (in Manual tab)
- [x] Clip tags visible (🔪 Prep, ✨ Hero, etc.)
- [x] Duration progress indicator (in Manual tab)

### 5. Header Bar (0.5 day)
- [x] Project name + edit status
- [x] Back to dashboard
- [x] Save button
- [x] Export button (moved to header)
- [x] Regenerate button (when processing)

## Technical Considerations
- Use a resizable split panel library (e.g., react-resizable-panels)
- Clip timeline drag: react-dnd or @dnd-kit
- Video player: consider video.js or custom HTML5 player
- Ensure backend APIs support all needed data in single fetch
- Test OOM: this page will load video + thumbnails + chat — watch memory

## Testing
- [ ] Full editor workflow: open project → watch video → chat with AI → manual rearrange → export
- [ ] ~~Resize panels~~ (not implemented - using fixed ratio for MVP)
- [ ] Mobile responsive layout (TODO: add breakpoints)
- [x] Drag/reorder clips in Manual tab grid
- [ ] Keyboard shortcuts (space = play - TODO)
- [ ] Performance with 18+ clips loaded

## Implementation Notes (Task 009)

### What Was Completed
1. **Complete redesign** of `/dashboard/project/[id]/page.tsx` into split-panel workspace
2. **Left panel (55%)**: Video preview, aspect ratio selector, Edit Summary Card
3. **Right panel (45%)**: Tabbed interface with two tabs:
   - **AI Chat tab**: Conversation history, prompt chips, undo/redo, chat input
   - **Manual tab**: Draggable clip grid, duration progress, AI notes, clip pool, Save/Render actions
4. **Bottom strip**: Horizontal clip timeline with thumbnails + Text overlays section
5. **Fixed header**: Project name, back button, save, export (context-aware)
6. **No scrolling**: Everything fits in viewport, overflow handled within panels
7. **Merged functionality**: Review & Arrange page functionality integrated into Manual tab

### Technical Changes
- Uses Flexbox for split panel layout (55/45 split)
- Each panel has independent `overflow-y-auto` for scrolling within
- Tab state managed with `activeTab` state variable
- Manual arrange state synced with edit plan data
- Drag & drop using HTML5 drag API
- All existing features preserved: conversation editing, text overlays, proxy preview, HD rendering

### Known Limitations / TODO
1. **No resizable panels**: Fixed 55/45 split (could add `react-resizable-panels` later)
2. **No mobile responsive**: Needs `@media` breakpoints to stack panels vertically
3. **No keyboard shortcuts**: Space for play/pause, arrow keys for seek, etc.
4. **No video seek on clip click**: Clicking timeline clips should jump video to that timestamp
5. **No current clip highlight**: Timeline should highlight which clip is currently playing
6. **Trim/speed controls**: Not exposed in UI (backend supports it via edit plan)

### What's Left from Original Checklist
- Mobile responsive breakpoints
- Keyboard shortcuts for video player
- Click-to-seek on timeline clips
- Real-time current clip tracking/highlight
- Panel resize handle (optional)

## Files Likely Involved
- `frontend/app/dashboard/project/[id]/page.tsx` — complete rewrite
- `frontend/app/dashboard/project/[id]/review/page.tsx` — merge into editor
- New components: SplitEditor, VideoPlayer, ClipTimeline, ChatPanel, ManualArrangePanel
- May need layout changes in `frontend/app/dashboard/layout.tsx`
