# Clip Timeline Redesign – Professional UI/UX Recommendations

**Author:** UI/UX Engineering Subagent  
**Date:** 2026-03-01  
**Project:** Videopeen - AI Cooking Video Editor  
**Task:** Redesign clip timeline cards to show thumbnail + label + duration + tag

---

## 🎯 Executive Summary

After analyzing the current 128px-wide cards and comparing against professional tools (CapCut, Premiere Pro, DaVinci Resolve), the timeline needs **wider cards** with a **two-layer information architecture** to avoid cramping while maintaining scannability across 10-25+ clips.

**Recommended card width: 160px** (previously 128px)  
**Key change: Add text description layer below thumbnail**

---

## 📊 Current Design Analysis

### What Works ✅
- Clean thumbnail visibility
- Color-coded badges are instantly recognizable
- Horizontal scrolling handles many clips
- Orange clip numbers provide quick reference

### Critical Issues ❌
1. **No context** – Users can't see what's happening without clicking/hovering
2. **128px is too narrow** to add text without severe truncation
3. **All info overlays thumbnail** – reduces visual clarity
4. **Duration placement** competes with clip number for space

---

## 🎨 Professional Tool Comparison

### CapCut Desktop Timeline
- **Card width:** ~180px
- **Layout:** Thumbnail + text label below (not overlaid)
- **Duration:** Small badge on thumbnail (top-right)
- **Type tags:** Icon-only badges (minimal)
- **Hover:** Expands card slightly, shows full text

### Premiere Pro
- **Card width:** ~150-200px (adjustable)
- **Layout:** Thumbnail with filename overlay at bottom (semi-transparent black bar)
- **Duration:** Numeric display at bottom-right of thumbnail
- **Type tags:** No colored badges (relies on track lanes)

### DaVinci Resolve
- **Card width:** Variable (120-240px)
- **Layout:** Thumbnail-focused, minimal text overlay
- **Duration:** Bottom-right on thumbnail
- **Type tags:** Small corner icons

### **Best Practice Synthesis:**
All pro tools use **either**:
1. Text label **below** thumbnail (CapCut) — cleaner, more readable
2. Semi-transparent text bar **over** thumbnail bottom (Premiere) — more compact

For cooking videos with **important visual content** (food!), **Option 1 is superior** — don't obscure the food with text overlays.

---

## ✨ Recommended Design

### Card Dimensions
```
Width: 160px (w-40)
Height: 140px total
  - Thumbnail: 90px (aspect-video, 16:9 = 90×50.6px)
  - Text area: 50px
```

### Layout Structure (Top to Bottom)

```
┌─────────────────────────────┐
│   [Tag Badge]       [Speed] │  ← Tag top-left, speed indicator top-right (if ≠1x)
│                             │
│      THUMBNAIL              │  90px tall, aspect-video
│                             │
│    #1           1.2s        │  ← Clip number (bottom-left) + duration (bottom-right)
├─────────────────────────────┤
│ Chopping onions             │  ← Short label (2 lines max, truncate)
└─────────────────────────────┘
```

### Component Breakdown

#### 1. Thumbnail Area (90px tall, aspect-video)
**Class:** `relative aspect-video h-[90px] overflow-hidden rounded-t-lg`

**Overlays on thumbnail:**
- **Tag badge** (top-left, 6px inset):  
  `absolute top-1.5 left-1.5 px-1.5 py-0.5 rounded text-[10px] font-semibold`
  - Keep current colors (e.g., `bg-orange-500 text-white` for Cook 🍳)
  - **Show emoji + first letter only** for compactness: `🍳 C`
  
- **Speed indicator** (top-right, only if speed_factor ≠ 1x):  
  `absolute top-1.5 right-1.5 px-1.5 py-0.5 rounded-md bg-black/70 text-white text-[10px] font-mono`
  - Example: `1.5×`, `0.5×`
  
- **Clip number** (bottom-left, 6px inset):  
  `absolute bottom-1.5 left-1.5 text-orange-400 text-xs font-bold drop-shadow-[0_1px_2px_rgba(0,0,0,0.8)]`
  - Example: `#1`, `#2`
  
- **Duration** (bottom-right, 6px inset):  
  `absolute bottom-1.5 right-1.5 text-gray-200 text-xs font-mono bg-black/50 px-1 rounded`
  - Example: `1.2s`, `0.8s`

#### 2. Text Label Area (50px tall)
**Container class:**  
`px-2 py-1.5 bg-zinc-800 border-t border-zinc-700 rounded-b-lg`

**Text class:**  
`text-xs text-gray-300 leading-tight line-clamp-2 break-words`

**Content source:**  
Use `description` field from clip data, truncate intelligently:
- **Max 2 lines** (line-clamp-2)
- **Smart truncation:** Prefer breaking at word boundaries
- **Character limit:** ~30-35 characters works well for 160px width

**Examples of good labels:**
- ✅ "Chopping onions"
- ✅ "Oil heating in pan"
- ✅ "Plating final dish"
- ✅ "Whisking eggs"
- ❌ "The chef carefully chops the onions into small pieces" (too long, truncate to "Chopping onions")

---

## 🎨 Tailwind Implementation

### Card Container
```jsx
<div className="
  group relative flex-shrink-0 
  w-40 h-[140px]
  cursor-pointer transition-all duration-200
  hover:ring-2 hover:ring-orange-500 hover:scale-105
  rounded-lg overflow-hidden
  bg-zinc-800
">
```

### Thumbnail Section
```jsx
<div className="relative aspect-video h-[90px] overflow-hidden rounded-t-lg bg-zinc-900">
  {/* Thumbnail image */}
  <img 
    src={clip.thumbnail} 
    alt="" 
    className="w-full h-full object-cover"
  />
  
  {/* Tag badge (top-left) */}
  <div className="absolute top-1.5 left-1.5 px-1.5 py-0.5 rounded bg-orange-500 text-white text-[10px] font-semibold flex items-center gap-0.5">
    <span>🍳</span>
    <span>C</span>
  </div>
  
  {/* Speed indicator (top-right, conditional) */}
  {clip.speed_factor !== 1 && (
    <div className="absolute top-1.5 right-1.5 px-1.5 py-0.5 rounded-md bg-black/70 text-white text-[10px] font-mono">
      {clip.speed_factor}×
    </div>
  )}
  
  {/* Clip number (bottom-left) */}
  <div className="absolute bottom-1.5 left-1.5 text-orange-400 text-xs font-bold drop-shadow-[0_1px_2px_rgba(0,0,0,0.8)]">
    #{clip.order}
  </div>
  
  {/* Duration (bottom-right) */}
  <div className="absolute bottom-1.5 right-1.5 text-gray-200 text-xs font-mono bg-black/50 px-1 rounded">
    {formatDuration(clip.end_time - clip.start_time)}
  </div>
</div>
```

### Text Label Section
```jsx
<div className="px-2 py-1.5 bg-zinc-800 border-t border-zinc-700 rounded-b-lg">
  <p className="text-xs text-gray-300 leading-tight line-clamp-2 break-words">
    {truncateLabel(clip.description, 35)}
  </p>
</div>
```

### Helper Functions
```javascript
// Format duration from seconds to readable string
function formatDuration(seconds) {
  if (seconds < 1) {
    return `${(seconds * 1000).toFixed(0)}ms`;
  }
  return `${seconds.toFixed(1)}s`;
}

// Intelligently truncate text
function truncateLabel(text, maxChars) {
  if (!text) return "Untitled clip";
  if (text.length <= maxChars) return text;
  
  // Try to break at word boundary
  const truncated = text.slice(0, maxChars);
  const lastSpace = truncated.lastIndexOf(' ');
  
  if (lastSpace > maxChars * 0.7) {
    return truncated.slice(0, lastSpace) + '…';
  }
  
  return truncated + '…';
}
```

---

## 🎭 Hover States & Interactions

### Hover Effect
```jsx
// On card container
className="
  hover:ring-2 hover:ring-orange-500 
  hover:scale-105 hover:z-10
  transition-all duration-200 ease-out
"
```

**Behavior:**
- Scale to 105% (slight zoom)
- Orange ring highlights active card
- Elevate with `z-10` so it appears above neighbors
- Smooth 200ms transition

### Active/Selected State
```jsx
// When clip is selected in timeline
className={`
  ${isSelected ? 'ring-2 ring-orange-500 scale-105 z-10' : ''}
`}
```

### Hover Tooltip (Optional Enhancement)
For clips with long descriptions, show full text in tooltip:

```jsx
<div 
  className="group/tooltip relative"
  title={clip.description} // Simple browser tooltip
>
  {/* Or custom tooltip with Radix UI / Headless UI */}
</div>
```

---

## 🎨 Tag Badge Color System

Keep current color scheme but ensure sufficient contrast:

```javascript
const tagStyles = {
  prep: 'bg-blue-500 text-white',      // 🔪 Prep
  cook: 'bg-orange-500 text-white',    // 🍳 Cook
  reveal: 'bg-purple-500 text-white',  // 🎬 Reveal
  mix: 'bg-green-500 text-white',      // 🥄 Mix
  hero: 'bg-yellow-500 text-black',    // ✨ Hero
  action: 'bg-red-500 text-white',     // ⚡ Action
  beauty: 'bg-pink-500 text-white',    // 📸 Beauty
};

// Compact display: emoji + first letter
function renderTag(actionType) {
  const config = {
    prep: { emoji: '🔪', letter: 'P', style: tagStyles.prep },
    cook: { emoji: '🍳', letter: 'C', style: tagStyles.cook },
    // ... etc
  };
  
  const { emoji, letter, style } = config[actionType] || config.prep;
  
  return (
    <div className={`px-1.5 py-0.5 rounded text-[10px] font-semibold flex items-center gap-0.5 ${style}`}>
      <span>{emoji}</span>
      <span>{letter}</span>
    </div>
  );
}
```

---

## 📐 Timeline Container Adjustments

Update the scrollable timeline container:

```jsx
<div className="
  flex gap-3
  overflow-x-auto overflow-y-hidden
  px-4 py-3
  scrollbar-thin scrollbar-thumb-zinc-600 scrollbar-track-zinc-800
">
  {clips.map(clip => (
    <ClipCard key={clip.clip_id} clip={clip} />
  ))}
</div>
```

**Gap between cards:** `gap-3` (12px) — enough breathing room, not too sparse

**Padding:** `px-4 py-3` — prevents cards from touching container edges

**Scrollbar:** Use custom thin scrollbar (requires Tailwind plugin or CSS):
```css
/* Add to global CSS if not using plugin */
.scrollbar-thin::-webkit-scrollbar {
  height: 8px;
}
.scrollbar-thin::-webkit-scrollbar-track {
  background: #27272a; /* zinc-800 */
}
.scrollbar-thin::-webkit-scrollbar-thumb {
  background: #52525b; /* zinc-600 */
  border-radius: 4px;
}
.scrollbar-thin::-webkit-scrollbar-thumb:hover {
  background: #71717a; /* zinc-500 */
}
```

---

## 🧪 Responsive Considerations

### For smaller screens (< 1024px)
```jsx
// Reduce card width to 140px
className="w-40 lg:w-36"
```

### For very wide screens (> 1920px)
Consider showing more visible cards at once, but keep card size fixed to maintain readability.

---

## 📊 Information Hierarchy (Visual Priority)

From **most** to **least** important:

1. **Thumbnail** (largest area, primary visual)
2. **Short label** (new! tells user what's happening)
3. **Tag badge** (quick category recognition)
4. **Clip number** (navigation reference)
5. **Duration** (technical detail)
6. **Speed indicator** (only when relevant)

**Design principle:** The eye should flow naturally from thumbnail → label → badges/numbers.

---

## 🚀 Implementation Checklist

- [ ] Update card container width from `w-32` (128px) to `w-40` (160px)
- [ ] Add 50px tall text label area below thumbnail
- [ ] Move tag badge to top-left of thumbnail (absolute positioning)
- [ ] Keep clip number at bottom-left with text shadow for readability
- [ ] Keep duration at bottom-right with dark background
- [ ] Add speed indicator (top-right, conditional) if `speed_factor !== 1`
- [ ] Implement `truncateLabel()` helper for description text
- [ ] Add hover states (scale + ring) to card
- [ ] Update timeline container gap to `gap-3`
- [ ] Test with 10, 15, 20, 25 clips to ensure scrolling works
- [ ] Verify text readability on various thumbnail backgrounds
- [ ] Add optional tooltip for full description on hover

---

## 🎯 Expected Outcome

**Before:** Small thumbnails with overlapping numbers/duration, no context about clip content.

**After:** Professional timeline where each clip clearly shows:
- What's happening (text label)
- Visual reference (thumbnail)
- Type of shot (tag badge)
- Order in sequence (clip number)
- Length (duration)
- Playback speed (if modified)

**User benefit:**  
Users can scan the timeline and immediately understand the video structure without playing each clip or hovering. This matches the workflow of professional editors who need to quickly navigate and reorder clips.

---

## 🔍 Alternative Design (If 160px Feels Too Wide)

If you must stay narrower, here's a **148px variant**:

```
Width: 148px (w-37, or custom class)
Thumbnail: 83px tall
Text area: 45px (smaller font, 1.5 lines)
Gap: 2 (8px)
```

**Trade-offs:**
- ✅ Fits more clips on screen
- ❌ Text truncates more aggressively
- ❌ Less breathing room

**Recommendation:** Stick with 160px. Horizontal scrolling is acceptable for 20+ clips; cramped cards are not.

---

## 📝 Final Notes

This design balances **information density** with **visual clarity**, following patterns from industry-leading tools. The key insight: **Don't overlay text on food thumbnails** — cooking videos are visual, and the food needs to be clearly visible at a glance.

The 160px width with dedicated text area gives room for meaningful labels while maintaining scannability across long timelines.

**Next steps:**
1. Implement the new card structure
2. Test with real clip data (especially long descriptions)
3. User test: Can someone understand the video structure from timeline alone?
4. Iterate on text truncation logic if needed

---

**End of Recommendations**  
Ready for implementation. 🚀
