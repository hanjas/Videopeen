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
- [ ] Replace single-column scrollable layout with CSS Grid or flexbox split panel
- [ ] Left panel (55-60%): Video preview + export format + summary card
- [ ] Right panel (40-45%): AI chat + manual arrange (tabbed)
- [ ] Bottom strip: Clip timeline + text overlays
- [ ] Responsive: on mobile, stack panels vertically
- [ ] No page scrolling — everything fits in viewport (overflow within panels)

### 2. Persistent Video Preview (1 day)
- [ ] Video player always visible in left panel
- [ ] Custom playback controls (play/pause, scrub, timestamp, volume, speed, fullscreen)
- [ ] Spacebar = play/pause shortcut
- [ ] Format toggle (9:16/1:1/16:9) below video

### 3. Tabbed Right Panel (2-3 days)
- [ ] Tab 1: AI Chat — conversational editing with history, prompt chips, undo/redo
- [ ] Tab 2: Manual Arrange — clip cards with drag/reorder, delete, trim controls
- [ ] Smooth tab switching, preserves state
- [ ] Merge current Review & Arrange page functionality into Tab 2

### 4. Draggable Clip Timeline (3-5 days)
- [ ] Bottom strip with real thumbnail frames
- [ ] Drag to reorder clips
- [ ] Click to jump video to that clip
- [ ] Highlight currently playing clip
- [ ] Delete (x), trim (scissors icon), speed controls on hover
- [ ] Clip tags visible (🔪 Prep, ✨ Hero, etc.)
- [ ] Duration progress indicator

### 5. Header Bar (0.5 day)
- [ ] Project name + edit status
- [ ] Back to dashboard
- [ ] Save button with auto-save indicator
- [ ] Export button (moved from mid-page to header)
- [ ] Regenerate button

## Technical Considerations
- Use a resizable split panel library (e.g., react-resizable-panels)
- Clip timeline drag: react-dnd or @dnd-kit
- Video player: consider video.js or custom HTML5 player
- Ensure backend APIs support all needed data in single fetch
- Test OOM: this page will load video + thumbnails + chat — watch memory

## Testing
- [ ] Full editor workflow: open project → watch video → chat with AI → manual rearrange → export
- [ ] Resize panels
- [ ] Mobile responsive layout
- [ ] Drag/reorder clips, verify video updates
- [ ] Keyboard shortcuts (space = play, ctrl+z = undo)
- [ ] Performance with 18+ clips loaded

## Files Likely Involved
- `frontend/app/dashboard/project/[id]/page.tsx` — complete rewrite
- `frontend/app/dashboard/project/[id]/review/page.tsx` — merge into editor
- New components: SplitEditor, VideoPlayer, ClipTimeline, ChatPanel, ManualArrangePanel
- May need layout changes in `frontend/app/dashboard/layout.tsx`
