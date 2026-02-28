# Agent Brainstorm Research - Compiled

## brainstorm-1-reorder-ui

## Videopeen — Post-Generation Clip Reorder Proposal

### Problem
AI-generated edit plans occasionally produce wrong clip ordering. Users need to fix this without re-running detection or edit planning.

### UX: Timeline Reorder View

After video generation, show a **horizontal timeline strip** with draggable clip cards. Each card displays:
- Thumbnail (extracted at midpoint of clip)
- Duration badge
- Action label from AI detection (e.g., "chopping onions", "adding salt")

**Interactions:**
- **Drag-and-drop** to reorder clips
- **Click card** to preview that clip in a side player
- **"Re-stitch" button** triggers backend reassembly
- **Undo/redo** stack for reorder history
- Optional: **delete clip** (X button) or **split at playhead**

Keep it dead simple — no full NLE. Just a sortable list with previews.

### Technical Approach

**Data model:** The edit plan is already a JSON array of clip descriptors:
```json
[
  { "id": "clip_03", "src": "raw.mp4", "start": 45.2, "end": 52.8, "label": "dice garlic" },
  { "id": "clip_01", "src": "raw.mp4", "start": 12.0, "end": 23.5, "label": "heat oil" }
]
```

**Frontend:** React + `dnd-kit` (lightweight drag library). Reordering mutates the array order client-side. On "Re-stitch", POST the reordered array to backend.

**Backend re-stitch endpoint:** `POST /projects/:id/restitch`
1. Receive reordered clip array
2. Generate ffmpeg concat demuxer file from the new order
3. Run: `ffmpeg -f concat -safe 0 -i list.txt -c copy output.mp4`
4. Using `-c copy` (stream copy) = **no re-encoding**, completes in seconds even for long videos
5. Return new video URL via webhook/polling

**Key optimization:** Since AI detection and clip boundaries are unchanged, only the concat order changes. Stream copy avoids transcoding entirely. A 10-minute video re-stitches in ~2-3 seconds.

**Storage:** Keep the original clip segments as intermediate files (don't delete after first render). This makes re-stitching a pure concat operation with zero reprocessing.

### Cost: ~3-4 days engineering
- 2 days: drag-and-drop timeline UI
- 1 day: restitch API endpoint
- 0.5 days: thumbnail extraction pipeline
- 0.5 days: testing/polish

## brainstorm-2-remove-swap



## Videopeen: Clip Remove/Replace Proposal

### Data Model

Store the edit plan as an ordered **clip manifest** — a JSON array of segment references:

```json
[
  {"id": "clip_01", "src": "raw_v1.mp4", "start": 0.0, "end": 12.4, "action": "chopping onions"},
  {"id": "clip_02", "src": "raw_v1.mp4", "start": 12.4, "end": 28.1, "action": "sautéing"},
  {"id": "clip_03", "src": "raw_v1.mp4", "start": 28.1, "end": 45.0, "action": "plating"}
]
```

Key insight: **never re-run action detection or frame extraction on edit**. The manifest is the single source of truth. Remove = delete entry. Replace = swap entry's source/timestamps.

### Backend: Re-stitch Without Re-processing

1. **On initial render**, pre-split raw video into per-clip segments (keyframe-aligned, stored in object storage). This is a one-time cost.
2. **Remove**: Drop clip from manifest → `ffmpeg -f concat` the remaining pre-cut segments. No decode/re-encode of untouched clips — use `-c copy` with segment files.
3. **Replace**: User uploads replacement footage OR picks from unused detected segments (show them a "cut room" of rejected clips). Swap the manifest entry, concat again.
4. **Render time**: Concat of pre-cut segments is ~seconds, not minutes. Only re-encode if transitions/effects span clip boundaries.

### UI Pattern: Timeline Strip

- Horizontal **filmstrip timeline** with thumbnail cards per clip, labeled by detected action.
- **Remove**: Click card → trash icon → card grays out with undo toast (soft delete, 5s).
- **Replace**: Click card → slide-up drawer showing (a) other detected-but-unused clips, (b) upload slot. Drag to swap.
- **Live preview**: On any edit, hit the concat endpoint — fast enough (<3s) to feel interactive. Show a spinner overlay on the preview player.
- **Reorder** via drag-and-drop on the strip (free bonus from the manifest model).

### Why This Works

- Zero re-processing of AI pipeline (detection, extraction all cached)
- Concat-only stitching = sub-5s renders for most edits
- Manifest is versionable → full undo history via JSON diffs
- UI is familiar (iMovie/CapCut mental model) but simplified to cooking-specific action cards

## brainstorm-3-ai-review



## Videopeen: Clip Ordering Correction — Proposal

### The Problem
AI-generated edit plans sometimes place clips out of chronological/logical order (e.g., plating before cooking, seasoning after serving).

### Solution: Two-Layer Correction System

**Layer 1: Automated Post-Generation Review**

After the AI generates an edit plan, run a second LLM pass with this prompt pattern:

```
Here's a cooking video edit plan with [N] clips. 
Review for logical/chronological errors:
- Does prep come before cooking?
- Does cooking come before plating?
- Are ingredient additions sequenced correctly?
Return: list of suggested swaps with reasoning, or "OK".
```

This catches obvious mistakes before the user ever sees them. Cost: one extra API call (~2-3 seconds). Apply fixes automatically if confidence is high, or present as suggestions if ambiguous.

**Layer 2: User-Flagged Correction**

In the timeline UI, let users right-click any clip → **"This is in the wrong position."** Then:

1. Send the flagged clip + surrounding context to the AI
2. AI analyzes the clip's content (transcript/visual description) against the full sequence
3. Returns 1-3 suggested positions with reasoning: *"This clip shows dicing onions — it likely belongs before the sautéing step (position 3→1)"*
4. User clicks to accept or drags manually

**Implementation specifics:**
- Store each clip's metadata: detected action (chopping, stirring, plating), ingredients visible, cooking state (raw/cooked)
- Use this metadata for ordering heuristics *before* the LLM review — cheap first pass
- Track user corrections as training signal: log original position → corrected position to fine-tune over time

**Priority order:**
1. Metadata heuristics (free, instant)
2. LLM review pass (cheap, automatic)  
3. User flag → AI suggestion (on-demand)

### Expected Impact
~70-80% of ordering errors caught at Layer 1. Remaining errors resolved in one click via Layer 2 instead of manual drag-and-drop.

## brainstorm-4-product



## Videopeen: Clip Ordering Fix — Product Proposal

### The Core Problem
AI-generated cooking videos sometimes misordered clips (e.g., plating before chopping). Users need a fast, low-friction way to correct this without rebuilding from scratch.

### Competitor Landscape
- **CapCut**: Full timeline editor — powerful but overwhelming for casual creators. AI features are additive, not primary.
- **Opus Clip**: AI-first, minimal editing. Lets users reorder clips via drag-and-drop card view + trim endpoints. No heavy timeline.
- **Vizard**: Similar card/strip approach. Preview → tweak → export. Light corrections only.

**Pattern**: AI-first tools use **card-based reordering**, not traditional timelines. This is the right model for Videopeen.

### Proposed MVP Editing Interface

**"Review & Fix" Screen** — shown after AI generates the video:

1. **Storyboard strip**: Horizontal row of thumbnail cards (one per clip). Drag to reorder. Tap to preview. That's it.
2. **Smart labels**: Each card auto-tagged with cooking stage (Prep → Cook → Plate → Serve). Makes misordering visually obvious.
3. **One-tap fix**: "Auto-reorder by cooking stage" button — uses the same AI to re-sort based on detected actions. Covers 80% of errors instantly.
4. **Split/merge**: Tap a card to split it or merge two adjacent cards. No timeline scrubbing needed.
5. **Regenerate clip**: If a clip is bad, "Replace" pulls the next-best segment from source footage.

### What Cooking Creators Care About Most
- **Recipe flow integrity** — steps in right order (non-negotiable)
- **Speed** — they batch-produce content; editing must take <5 min
- **B-roll auto-insert** — close-ups of sizzling, pouring, etc.
- **Text overlays** — ingredient lists, step numbers (auto-generated)

### The Balance
AI handles first draft (80% right). User fixes the 20% via storyboard cards. Never force them into a full timeline. The principle: **AI proposes, human reorders, AI re-renders.**

### Next Step
Build the storyboard strip as a standalone component. Test with 10 cooking creators. Measure: time-to-export and reorder frequency.

## brainstorm-5-fast-restitch



## Videopeen: Fast Re-Stitch Architecture

### Core Principle: **Never re-encode. Only re-mux.**

---

### 1. Clip Storage Layer

All intermediate clips stored as **individually encoded MP4s** with identical encoding parameters:
- Same codec (H.264/H.265), profile, level
- Same resolution, frame rate, pixel format
- Same audio sample rate/channels (AAC 48kHz stereo)
- **Each clip starts on a keyframe** (critical for concat demuxer)

Store clips at: `clips/{project_id}/{clip_id}.mp4` — never delete until project archived.

### 2. Re-Stitch via FFmpeg Concat Demuxer

Generate a text manifest:
```
file 'clip_003.mp4'
file 'clip_001.mp4'
file 'clip_007.mp4'
```

Execute:
```bash
ffmpeg -f concat -safe 0 -i manifest.txt -c copy -movflags +faststart output.mp4
```

`-c copy` = **zero re-encoding**. This runs in **1-3 seconds** regardless of total duration because it's just copying packet streams and rewriting the container.

### 3. Ensuring Seamless Concatenation

The reason this fails in practice: mismatched stream parameters. **Enforce at clip creation time:**
- Transcode all source clips to a **canonical format** during initial ingest (the slow step, done once)
- Use `-force_key_frames "expr:eq(mod(n,1),0)"` or ensure each clip starts with an IDR frame
- Normalize timestamps: `-avoid_negative_ts make_zero`

### 4. Architecture

```
[User reorders clips in UI]
       ↓
[API generates manifest.txt] — ~1ms
       ↓
[ffmpeg concat demuxer, -c copy] — ~2s
       ↓
[Upload to CDN / return presigned URL]
```

### 5. Edge Cases

- **Transitions/effects between clips**: Pre-render transition segments as their own clips (`transition_3_to_1.mp4`), include in manifest. Cache common transitions.
- **Trimming within a clip**: Use `-ss`/`-to` with `-c copy` (cuts at nearest keyframe). For frame-accurate cuts, pre-render the trimmed clip once, cache it.
- **Audio normalization**: Apply during initial ingest, not at stitch time.

### Result

Initial render: 15 min (unchanged). **Every subsequent re-order/removal: 1-3 seconds.** The manifest is the project state — versioning is trivial.

## brainstorm-6-trim-adjust

## Videopeen — Clip Duration Adjustment Proposal

### UX: Timeline Strip with Drag Handles

Each clip in the AI-generated edit appears as a colored block on a horizontal timeline. Non-technical creators interact with three gestures:

1. **Drag edges** — Grab left/right handles to trim start/end points. A thumbnail preview scrubs in real-time as you drag, snapping to cut-safe points (between sentences, at natural pauses the AI detected).

2. **Pinch/stretch** — Long-press a clip to enter speed mode. Drag wider = slow-mo, narrower = speed-up. A badge shows "1.5×" or "0.5×". Constrain range to 0.25×–4× to keep things usable.

3. **Split & nudge** — Tap a clip to place a playhead, tap "split" to slice it. Now each segment is independently trimmable. This handles "I want the plating shot longer but the stirring shorter" within what was one clip.

**Preview:** Instant scrubbing with no spinner. Show a toast: "Final export may differ slightly" since preview uses a lighter pipeline.

### Backend Architecture

**Source files stay untouched.** The edit is a lightweight JSON manifest:

```json
{
  "clips": [
    { "source": "raw_03.mp4", "in": 12.847, "out": 19.203, "speed": 1.0 },
    { "source": "raw_01.mp4", "in": 3.400, "out": 8.100, "speed": 2.0 }
  ]
}
```

**Preview without re-encoding:** Use server-side keyframe index + client-side `<video>` with `MediaSource Extensions`. For scrubbing between keyframes, decode the nearest GOP on a Web Worker using FFmpeg/WASM (lightweight, ~2MB). This gives frame-accurate preview at interactive speed without a full transcode.

**Frame-accurate trimming on export:** Final render uses FFmpeg server-side with `-ss` (input seeking) + `-to` with `setpts`/`atempo` filters for speed changes. Re-encode only affected segments; copy-mux the rest.

**Speed changes:** Handled via `setpts=PTS/1.5` (video) + `atempo=1.5` (audio). Preview approximates this client-side by adjusting `HTMLVideoElement.playbackRate`.

### Key Principle

Every user action edits the manifest, never the source. Undo is just manifest rollback. Cheap, instant, non-destructive.

## brainstorm-7-add-missed



## Proposal: "Add Missed Clip" Feature for Videopeen

### User Flow

1. **Timeline "+" Button** — Between every clip on the edit timeline, show a subtle `+` icon on hover. Tapping it opens the **Clip Browser** anchored to that insertion point.

2. **Clip Browser (Unused Moments)** — A filmstrip-style drawer slides up showing thumbnail cards of footage segments the AI *didn't* use. Each card shows: a representative frame, timestamp range, and an AI-generated label ("cheese pull," "plating close-up," "pan flip"). Users can scroll horizontally or filter by tag/keyword.

3. **Preview & Trim** — Tapping a thumbnail plays an inline preview. Drag handles let users trim the in/out points. A "fit check" indicator shows whether the clip's visual style (lighting, angle) matches its neighbors.

4. **Insert & Auto-adjust** — Hit "Insert." The clip drops into the timeline at the chosen gap. Backend auto-applies color grading to match adjacent clips and crossfade transitions. Background music and voiceover timing re-adjust automatically.

### Backend Design

- **Scene Segmentation (ingest time):** During upload, split raw footage into segments using shot detection + action recognition. Store each segment with: timestamps, embedding vector, AI tags, thumbnail, and a `used: bool` flag.
- **Unused Segments Index:** Query is just `WHERE used = false ORDER BY timestamp`. Cheap and fast.
- **On Insert:** Update the edit graph (ordered list of segment IDs). Re-run the audio/transition pipeline on the affected 3-clip window only (not the whole video) for near-instant results.
- **Embeddings for search:** If the user types "cheese pull," do a semantic search against segment embeddings. Much better than tag-only filtering.

### Where It Fits

This goes in the **Review & Refine** step — after AI generates the first cut, before final export. It's the human override layer: AI proposes, user disposes.

**Key principle:** Never throw away footage metadata. Every unused frame is a candidate. The AI's first cut is a draft, not a verdict.

## brainstorm-8-variations

## Videopeen: Edit Variations Proposal

### Core Insight
The expensive part is **analysis**, not **editing decisions**. Split them.

### Architecture: Analyze Once, Plan Many, Render On-Pick

**Phase 1 — Shared Analysis (done once)**
- Action detection, scene segmentation, ingredient recognition
- Audio transcription + beat detection
- Quality scoring per clip (sharpness, framing, lighting)
- Output: **Clip Manifest** — a structured index of every usable moment with metadata

**Phase 2 — Variation Planning (near-zero cost)**
- Feed the Clip Manifest to an LLM with 3 different system prompts:
  - **"Clean & Classic"** — chronological, minimal cuts, longer shots
  - **"Fast & Punchy"** — jump cuts, montage-heavy, TikTok pacing
  - **"Story-Driven"** — starts with finished dish, flashback structure, emotional beats
- Output: 3 **Edit Decision Lists (EDLs)** — just JSON arrays of `{clipId, in, out, transition, speed}`. Kilobytes of text.

**Phase 3 — Preview (cheap)**
- Generate low-res storyboard strips from each EDL using already-extracted keyframes
- User sees 3 visual timelines side-by-side, can tap to preview segments
- No full render yet

**Phase 4 — Render On Demand**
- User picks one variation (or frankenstein-mixes segments across variations)
- Only then: full-resolution stitching, color grading, audio mixing
- Single render pass

### Cost Breakdown
| Phase | Relative Cost |
|-------|--------------|
| Analysis | 1.0x (shared) |
| 3 Edit Plans | ~0.01x (LLM text gen) |
| Previews | ~0.05x (keyframe assembly) |
| Final Render | 1.0x (one variation only) |

**Total: ~1.06x instead of 3x.**

### Mixing UX
Let users drag segments between variation timelines. "I like the intro from Punchy but the technique section from Classic." The EDLs are just arrays — splicing is trivial.

### Key Tradeoff
Previews aren't pixel-perfect. Transitions and speed ramps only fully resolve on final render. Acceptable for a "pick your vibe" workflow.

## brainstorm-9-preview



# Videopeen Preview: Proposal

## Architecture: Playlist-Based Browser Preview

**Skip stitching entirely for preview.** Don't combine clips into one video — play them sequentially.

### Core Approach: Virtual Timeline Player

Build a custom player (HTML5 `<video>` + JS) that maintains an **edit decision list (EDL)** — an ordered array of `{src, inPoint, outPoint}`. On playback:

1. Preload the next 2-3 clips while current plays
2. At each clip boundary, swap `<video>.src` (or toggle between 2-3 pre-loaded video elements for gapless playback)
3. Trims = just adjust `inPoint`/`outPoint` + `currentTime` seek. Zero processing.
4. Reorder = reorder the array. Instant.

**Gap between clips:** Use two `<video>` elements overlapping. Element B starts loading when A hits ~2s remaining. Crossfade or hard-cut via CSS opacity. Achieves <50ms transition gaps — imperceptible.

### What About Transitions/Text Overlays?

Layer a `<canvas>` on top of the video elements. Render text, lower-thirds, watermarks via 2D canvas. For crossfade transitions, briefly draw both frames to canvas using `drawImage()` from each video element. No WebGL needed for cooking videos.

### Dual-Resolution Strategy

- **On upload:** Generate a 480p proxy (fast, ~10s per minute of footage via FFmpeg preset `ultrafast`). Store alongside original.
- **Preview plays proxies.** Scrubbing and playback stay snappy.
- **Final render:** Server-side FFmpeg concatenates originals using the EDL. This is the only time full encoding happens.

### Why Not WebCodecs/WASM FFmpeg?

Overkill for a small SaaS. Browser compat is spotty, debugging is painful, and you don't need frame-level precision for a cooking video editor. The playlist approach handles 95% of use cases with standard web APIs.

### Implementation Cost

- Custom player: ~1-2 weeks
- Proxy generation pipeline: ~2-3 days (FFmpeg + queue)
- Server-side final render: ~1 week

**Total: ~3 weeks to production-ready preview.** Ship the playlist player first (week 1), add proxy generation after.

## brainstorm-10-full-journey



# Videopeen: Post-Generation Editing Flow

## The Screen

Split layout: **video preview** (left, 60%) + **edit panel** (right, 40%). Below the video: a simple **scene timeline** — not a traditional timeline, but visual cards representing each scene (e.g., "Intro," "Chopping Onions," "Simmering," "Plating").

## User Actions

**Scene-level edits** (click any scene card):
- **Swap clip** — regenerate just that scene with a different style/angle
- **Trim/extend** — slider to shorten or lengthen
- **Change text overlay** — edit captions, titles, ingredient callouts inline
- **Replace voiceover** — re-record or type new narration for AI voice

**Global edits** (top of edit panel):
- **Music** — swap background track from curated library
- **Pacing** — "Faster / Normal / Slower" toggle (adjusts all scenes proportionally)
- **Style** — color grading presets ("Warm Kitchen," "Clean & Bright," "Moody")
- **Captions** — toggle on/off, pick font/position

**Chat-based edits** (bottom of panel):
- Natural language box: *"Make the intro shorter and add a close-up of the garlic"* — AI interprets and applies changes. This is the power move for non-pros.

## Preview

Every edit triggers a **fast preview render** (lower quality, ~5s wait). User watches inline. Yellow dots on the timeline mark changed scenes. **Undo/redo** always available.

## Finalize

Big **"Looks Good"** button → picks export format (Reel/TikTok/YouTube/Square) → full-quality render (background, notification when done) → download or **one-click publish** to connected platforms.

## Key Principle

No video editing vocabulary. No "tracks," "keyframes," or "layers." Everything is **scene cards + sliders + chat**. A home cook who posts recipes on Instagram should feel at home in 30 seconds.

## review-1-critic



**Critical Review: Videopeen Post-Generation Editing**

**Will break:**

- **"concat copy" is a lie for trimmed/speed-changed clips.** `-c copy` only works when you're joining whole files with identical codecs, resolutions, and keyframe alignment. The moment someone trims mid-GOP or changes speed, you're re-encoding. That "1-3 seconds" becomes 10-30+ seconds. Your entire fast-restitch premise collapses for 2 of 5 user actions.

- **Gapless dual-video-element playback is harder than it sounds.** Browser video decode is async. You'll get flashes, micro-gaps, or audio pops on slower devices/mobile Safari. This will feel broken and you'll burn days debugging per-browser quirks. Budget for this.

**Missing:**

- **Audio continuity.** Reordering clips means jarring audio cuts mid-sentence or mid-ambient-sound. No mention of crossfades, even simple ones. Users will think the output is broken.

- **Keyframe alignment strategy.** If clips aren't cut on keyframes, concat copy produces garbled frames at boundaries. Are you forcing keyframes at clip boundaries during initial generation? If not, nothing works.

- **State management.** Undo/redo beyond a single "undo toast" for remove. Users will reorder 5 things, hate it, want to go back. You need an edit history stack.

- **Mobile.** Drag-and-drop on mobile is painful. If your users are cooking-content creators, many shoot and edit on phones.

**Over-engineered for MVP:**

- **AI auto-fix ordering.** Cut it entirely from MVP. You're adding a second LLM call, building review UI, handling disagreements between AI and user intent—all for an edge case. Let users drag clips manually. Ship AI-fix in v2 when you have data on whether ordering is actually a problem.

- **"Browse unused AI-detected actions"** implies maintaining a parallel inventory of unselected clips with metadata. That's a feature, not a button. Defer it.

**MVP should be:** pre-keyframed clips → reorder cards → remove → concat copy (whole clips only) → download. Four things. Ship in a week.

## review-2-prioritize

## Videopeen MVP: Ruthless Prioritization

### Build These 2 Things Only

**1. Remove clip (easiest, highest value)**
Cooking creators' #1 pain: "that clip is garbage, delete it." One click remove + auto-restitch. This alone is worth paying for because the alternative is re-editing in Premiere/CapCut.

**2. Drag-drop reorder + restitch**
"I filmed the garnish before the sauce" — reorder and export. Combined with remove, this covers 80% of post-generation editing needs. The ffmpeg concat copy approach (2-3s export) is your killer differentiator vs. cloud editors that take minutes.

### Cut From MVP

- **AI auto-fix ordering** — Cut entirely. It's cool but it's R&D risk. You'll spend weeks on prompt engineering, edge cases, and it won't be reliable enough for v1. Add it in month 2 when you have real user clips to test against.
- **Trim/speed adjust** — Cut. This requires re-encoding (no more concat copy speed trick). Complexity explodes. Every video editor already does this. It's not your differentiator.
- **Add missed clips** — Cut. Upload + insert UX is complex. Users can work around this by generating a new clip and reordering.

### The Minimum Viable Product

A page showing your generated clips as thumbnails. Drag to reorder. Click X to remove. Hit "Export" → 2-3 second restitch → download link.

That's it. **Ship in 1-2 weeks.**

### Why This Works

Cooking creators don't need another full editor. They need the **last mile**: "my AI-generated cooking video is 90% right, let me fix the 10%." Remove + reorder handles that. The speed (2-3s export) is the moat — nobody else gives you that because they're all re-encoding.

### One Warning

Browser-based preview via sequential `<video>` elements will have visible seams between clips. Don't over-engineer this — a simple playlist with 100ms gaps is fine for preview. The exported file is what matters.

## review-3-technical



## Technical Gotchas

**ffmpeg concat demuxer (`-c copy`) will break if:**
- Clips have different codecs, resolutions, frame rates, sample rates, or pixel formats. Concat copy does zero transcoding — mismatched parameters produce corrupted output or playback errors. You MUST enforce identical encoding params at clip creation time (resolution, fps, profile/level, audio sample rate, channel layout).
- Clips don't start on keyframes. If a clip doesn't begin with an IDR frame, the concatenation point will show corruption/green frames until the next keyframe. Ensure every clip starts with `-force_key_frames 0` or equivalent.
- Audio codec uses priming samples (AAC has ~2048 samples of encoder delay). Each clip boundary accumulates this delay, causing A/V drift that grows with clip count. After 10+ clips you'll notice. Fix: use `editlist=0` or trim priming samples explicitly.
- Timestamps aren't monotonic. Concat demuxer can produce DTS discontinuities causing players to stutter or skip. Use `-avoid_negative_ts make_start_zero` on each clip.

**Browser gapless playback — harder than it sounds:**
- `HTMLMediaElement` has no frame-accurate swap guarantee. Even with two `<video>` elements and `preload="auto"`, you'll get 1-3 frame gaps on swap due to browser decode buffer latency. The `timeupdate` event fires at ~250ms granularity — too coarse for frame-accurate switching.
- Better approach: use MSE (Media Source Extensions) to feed segments into a single player, or use `requestVideoFrameCallback()` for frame-accurate timing (Chrome/Edge only, no Safari until recently).
- Mobile browsers aggressively suspend background video elements. Your preloaded second `<video>` may get evicted, causing a visible pause on swap.
- Different clips with slightly different audio sample rates will produce audible pops/clicks at boundaries even if video looks fine.

**Edge cases that will bite you:**
- Variable frame rate source footage (common from phones) — concat produces timestamp chaos
- Clips shorter than one GOP (~2s) — may lack keyframes entirely
- B-frame reordering across concat boundaries

## review-4-user-perspective



**As a cooking creator reviewing my AI-generated edit:**

**What feels intuitive:** Scene cards are perfect for recipe videos — I already think in steps (prep, sauté, plate). Drag-drop reorder makes sense if the AI got my sequence wrong. Remove/add clips is obvious. This feels like editing a recipe, not editing a video. Love that.

**What's confusing/concerning:**
- **"AI Auto-Fix" — fix WHAT?** This is too vague. Does it fix pacing? Color? Audio? I need to trust it before I click it. Show me what it'll change first, or let me undo instantly.
- **Trim/speed per clip** — how precise? If I can't set an exact cut point for when my sauce starts bubbling vs. when I'm just standing there, it's useless. CapCut gives me frame-level control.
- **Where's my text/captions?** Recipe videos NEED text overlays — ingredient lists, step labels, "Season to taste 🧂". If I still have to export and add text in CapCut, you've lost me.
- **Where's audio control?** Background music, voiceover timing, sizzle sounds — audio is half the video. No mention of this is a red flag.

**What's missing:**
- Auto-generated captions/subtitles (non-negotiable for TikTok/Reels)
- Aspect ratio switching (9:16, 1:1, 16:9) from one edit
- Templates for my brand (consistent fonts, colors, intro/outro)
- Direct publish to TikTok/Instagram

**Would I pay $25/month?** Not yet. Right now this sounds like it handles maybe 40% of my workflow. I'd still need CapCut for text, audio, and captions. If you nail auto-captions, text overlays, music, and one-click publish — yes, $25 is a steal compared to the 2-3 hours I spend per video.

**What makes me switch from CapCut?** Speed. If I can go from raw footage to publishable video in under 15 minutes instead of 90, I'll switch tomorrow. But "publishable" means captions, music, and text included — not just cuts.

## review-5-business



**Honest take: Post-generation editing is necessary but won't drive revenue. Build it lean, then focus elsewhere.**

**Why $25/mo is a hard sell right now:** Your competition is CapCut (free), Descript, and generic AI video tools. "AI cooking video editor" is niche — good for positioning, bad for market size. The people making cooking content are either hobbyists (won't pay) or creators/brands (need more than editing).

**What actually drives paying users:**

1. **Output quality that saves real time.** If your 15-min pipeline replaces 2+ hours of manual editing with genuinely good results, that's the pitch. Not features — *time saved with acceptable quality.*
2. **Distribution, not just editing.** Auto-format for Reels/TikTok/YouTube Shorts (different aspect ratios, captions, hooks). This is where creators feel pain. Edit once → export everywhere is worth $25/mo.
3. **Auto-captions + ingredient overlays.** Cooking-specific value-adds that generic tools can't match. Recipe card generation from the video. *This* is your moat.

**What to build next (priority order):**

1. **Multi-format export** (9:16, 1:1, 16:9) with auto-reframing — 2-3 days of work, massive perceived value
2. **Auto-captions with ingredient detection** — cooking-specific, defensible
3. **Minimal post-gen editing** (reorder/remove clips only, skip trim/AI auto-fix for now) — table stakes, don't over-invest
4. **Share/embed link** — let users show output without downloading

**Skip for now:** Collaboration, music library (licensing nightmare), complex timeline editing (you'll never beat Descript).

**The real advice:** You have ~0 users. Spend 50% of your time on distribution, not features. Post before/after videos on cooking subreddits and TikTok. Find 10 food bloggers, offer it free, get testimonials. The BYOK free tier is smart for acquisition — but only if people know you exist.

**Moat:** Cooking-domain AI (ingredient detection, recipe understanding) + speed. Go deeper into cooking, not wider into generic video editing.

## deep-1-data-model



# Videopeen: Edit Plan Data Model

## MongoDB Collections

### `editPlans`
```javascript
{
  _id: ObjectId,
  projectId: ObjectId,        // ref → projects
  userId: ObjectId,
  status: "draft" | "confirmed" | "rendering" | "rendered" | "failed",
  
  // Version tracking (undo/redo)
  version: 3,                 // current version number
  history: [                  // append-only log
    {
      version: 1,
      source: "ai",           // "ai" | "user"
      action: "initial_generation",
      timestamp: ISODate,
      snapshot: "<gridfs_ref or BSON>"  // full timeline state at this version
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
        sourceFileId: ObjectId,         // ref → raw upload
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
          sceneQuality: 0.85,           // blur, lighting, framing score
          suggestedTransition: "crossfade",
          reasoning: "Clear overhead shot of knife technique"
        },
        
        // User overrides (null = unchanged from AI)
        overrides: {
          label: null,
          inPoint: 13.0,               // user trimmed start
          outPoint: null,
          transition: "cut"
        },
        
        // State
        status: "included",            // "included" | "excluded" | "added_by_user"
        addedBy: "ai",                 // "ai" | "user"
        thumbnailUrl: "https://...",
        waveformData: [...]            // for audio preview
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
      rejectionReason: "low_quality",  // why AI excluded it
      status: "excluded"
    }
  ],
  
  aiModel: { name: "videopeen-v2.1", runId: "run_abc123" },
  createdAt: ISODate,
  updatedAt: ISODate
}
```

## Key Design Decisions

**Undo/Redo**: Each edit appends to `history` with a full snapshot. `currentVersionPointer` tracks position — undo decrements, redo increments. Snapshots beyond pointer get pruned on new edits (fork behavior).

**AI vs User tracking**: `addedBy` marks origin. `overrides` object keeps user changes separate from AI values — you can always diff or revert to AI suggestion per-field.

**Excluded clips**: `clipPool` holds everything AI detected. `timeline.clips` is the active edit. Users drag from pool → timeline (status flip). `rejectionReason` explains AI's decision.

**Indexes**: `{ projectId, userId }`, `{ status }`, `{ "timeline.clips.clipId": 1 }`.

## deep-2-ui-design



# Review & Arrange Screen — UI/UX Design

## Layout (Desktop)
Full-screen dark canvas (`#0D0D0F`). Three zones:

**Top Bar** — Project name (editable inline), total duration badge (`3:42`), undo/redo arrows, "Preview" button (ghost, orange border), "Render Final" button (solid orange `#FF6B2C`, pill-shaped, right-aligned).

**Main Timeline (center, 65% height)** — Horizontal scrollable strip of clip cards. Cards snap to a grid with 8px gaps. Drop zones glow orange on drag-hover. A thin orange progress line spans the bottom showing total video duration with tick marks.

**Unused Clips Drawer (bottom, 30% height)** — Collapsible panel with header: "Available Clips (7)" + chevron toggle. Grid layout (3-4 columns). Clips here are slightly desaturated. Drag up to add; drag down from timeline to remove.

## Clip Card Design
**Size:** 180×120px (timeline), 140×96px (drawer).
Each card shows:
- **Thumbnail** — keyframe with 2px rounded corners, subtle hover zoom (1.03×)
- **Duration pill** — bottom-right overlay, `0:14`, semi-transparent black bg
- **Action label** — bottom-left, bold 11px, e.g. "Searing the steak"
- **Cooking stage badge** — top-left colored dot + label: 🟢 Prep / 🟡 Cook / 🔴 Plating
- **Drag handle** — 6-dot grip icon, top-right, visible on hover
- **Remove button** — `×` icon, top-right on hover (timeline cards only)

**Selected state:** orange border 2px. **Dragging state:** slight rotation (2°), elevated shadow, 80% opacity at origin.

## Drag & Drop
`dnd-kit` library. Smooth spring animation on reorder. Orange insertion indicator (vertical 3px bar) between cards. Dragging from drawer to timeline auto-expands a gap. Cards animate closed when removed.

## Preview Playback
Clicking "Preview" opens a centered modal (70vw) with a stitched low-res preview. Scrub bar maps to clip boundaries with subtle dividers. Close with Esc or `×`.

## Mobile (< 768px)
Timeline becomes vertical stack (full-width cards, 100×80px thumbnails). Unused clips in a bottom sheet (swipe up). Long-press to drag. "Render Final" becomes sticky bottom CTA bar.

## Micro-interactions
- Card entry: staggered fade-up (50ms delay each)
- Reorder: 200ms spring ease
- Remove: card shrinks + fades, siblings slide in
- Render button: subtle pulse animation when arrangement differs from AI default

## deep-3-preview-system



# Preview Before Render — System Design

## Architecture

**Thumbnail Pipeline:** On upload, FFmpeg extracts keyframe thumbnails (WebP, 320px wide) at 1-second intervals server-side, stored on CDN. This powers scrubbing without loading video. Generate a sprite sheet per clip (10×10 grid) for instant hover previews — one HTTP request per clip.

## Clip Cards View

Each edit decision renders as a **card** in a horizontal scrollable timeline: thumbnail, duration badge, trim indicators, transition type between cards. Cards are **draggable** for reorder. Click a card → inline `<video>` player loads that segment with `#t=start,end` media fragment — no custom player needed for basic preview.

## Sequence Playback Engine

**The core problem:** seamless gapless playback across heterogeneous clips without rendering.

**Solution: Double-buffer `<video>` elements.** Two video elements, alternating. While clip A plays, clip B preloads the next segment. On clip A's `timeupdate` near end, crossfade to B. This gives near-seamless playback without MSE complexity.

**Why not MediaSource Extensions?** MSE requires uniform codec/container. Cooking videos come from phones (H.264, H.265, varying profiles). Transcoding defeats "preview before render." Double-buffering works with any browser-playable format as-is.

**Fallback:** If a source codec isn't browser-playable (HEVC on Firefox), serve a lightweight proxy transcode (720p H.264 baseline) generated async post-upload. Flag it: *"Preview quality — full resolution on render."*

## Timeline Scrubbing

A `<canvas>`-drawn timeline bar showing sprite thumbnails. On hover/drag: render the corresponding sprite frame to a tooltip canvas. On click: seek the relevant `<video>` element to that timestamp. Touch-friendly: 44px minimum hit target, momentum scrolling on the card rail.

## Playback Indicator

A `requestAnimationFrame` loop syncs a CSS-transformed playhead to `video.currentTime`. Progress bar fills proportionally across **all clips** (accumulated durations). Current card highlights with a ring/border.

## Performance

- **Lazy load** video sources — only the visible card ± 1 neighbor loads `<video src>`
- **IntersectionObserver** on cards triggers preload
- Sprite sheets cached in `CacheStorage` via service worker
- Mobile: cap proxy at 480p, reduce sprite density to every 2s
- Total timeline state lives in a lightweight JSON structure — serializable, undo/redo trivial

## Mobile

Horizontal card scroll with snap points (`scroll-snap-type`). Tap-to-play replaces hover. Fullscreen playback delegates to native `<video>` controls via `playsinline` + `webkit-playsinline`.

---

**Result:** Users see, scrub, reorder, and play their full edit sequence — all in-browser, zero render wait, works on any device.

## deep-4-backend-arch



## Videopeen: Clip Review & Render Architecture

### Data Model (MongoDB)

```python
# EditPlan document
{
  "_id": ObjectId,
  "project_id": ObjectId,
  "status": "draft|confirmed|rendering|completed|failed",
  "clips": [{
    "clip_id": str,  # uuid4
    "source_file": str,
    "start_ms": int,
    "end_ms": int,
    "order": int,
    "thumbnail_path": str | None,
    "transitions": {"type": "crossfade", "duration_ms": 500}
  }],
  "render_job_id": str | None,
  "output_url": str | None,
  "created_at": datetime,
  "updated_at": datetime
}
```

### API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/projects/{id}/edit-plan` | Get current edit plan |
| `PATCH` | `/projects/{id}/edit-plan` | Reorder/add/remove clips (accepts full clips array) |
| `POST` | `/projects/{id}/edit-plan/confirm` | Lock plan, enqueue render |
| `GET` | `/clips/{clip_id}/thumbnail` | Redirect to thumbnail (generated lazily) |
| `GET` | `/clips/{clip_id}/preview` | Stream low-res clip segment |
| `WS` | `/projects/{id}/render/progress` | Real-time render progress |

### Clip Storage: On-Demand with Cache

Don't pre-cut clips. Store only timestamps. Generate thumbnails/previews on first request, cache to S3/local:

```python
async def get_thumbnail(clip):
    cache_key = f"thumb/{clip.clip_id}.jpg"
    if not await storage.exists(cache_key):
        await ffmpeg_extract_frame(clip.source_file, clip.start_ms + (clip.end_ms - clip.start_ms) // 2, cache_key)
    return cache_key
```

### Render Queue (Celery + Redis)

```python
@celery.task(bind=True, max_retries=2)
def render_video(self, plan_id: str):
    plan = db.edit_plans.find_one({"_id": plan_id})
    total = len(plan["clips"])
    
    # Build ffmpeg concat filter
    for i, clip in enumerate(plan["clips"]):
        extract_segment(clip)  # cut to temp/
        redis.publish(f"render:{plan_id}", json.dumps({"step": "cutting", "progress": (i+1)/total}))
    
    concat_and_encode(plan_id)  # final render
    redis.publish(f"render:{plan_id}", json.dumps({"step": "done", "url": output_url}))
```

### WebSocket Progress

```python
@router.websocket("/projects/{id}/render/progress")
async def ws_progress(ws: WebSocket, id: str):
    await ws.accept()
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"render:{id}")
    async for msg in pubsub.listen():
        await ws.send_text(msg["data"])
```

### Cleanup & Error Handling

- **Temp files**: Celery `after_return` signal deletes `temp/{plan_id}/` regardless of success/failure
- **Stale renders**: Celery Beat task marks `rendering` jobs older than 30min as `failed`, cleans temp
- **Confirm endpoint** sets `status=confirmed` atomically with `$set` + version check to prevent double-submit
- **PATCH validation**: Rejects if status ≠ `draft`; validates all clip timestamps against source duration

### Key Decisions

1. **On-demand over pre-cut** — saves storage, thumbnails cached after first hit
2. **Celery over in-process** — render is CPU-heavy, must not block API workers
3. **Redis pub/sub for WS** — decouples render worker from API; scales horizontally
4. **Atomic status transitions** — MongoDB `find_one_and_update` with status precondition prevents race conditions

## deep-5-clip-library



# Clip Library — Unused Clips System

## Data Model

Every detected action gets a `ClipAction` record regardless of whether AI selected it:

```
ClipAction {
  id, sourceTimestamp, duration,
  stage: prep | cook | plate | other,
  label: "dicing onions" | "flambé" | ...,
  qualityScore: 0-100,        // AI confidence + technical quality (blur, exposure, framing)
  aiSelected: boolean,
  thumbnailUrl, previewUrl,    // pre-generated on ingest
  tags: string[]               // auto-generated: "close-up", "hands", "plating", etc.
}
```

## UI: Clip Library Panel

Collapsible right-side panel (like Premiere's media browser), toggled via toolbar icon with badge showing unused clip count.

**Layout:**
- **Top bar:** Search field + filter chips: `Stage` (prep/cook/plate) · `Quality` (★★★+) · `Not in edit` toggle (default on)
- **Body:** Thumbnail grid (3-col, 120px cards). Each card shows:
  - Thumbnail with duration badge (bottom-right)
  - Action label ("Slicing garlic")
  - Quality dots (●●●○○) — green/yellow/red
  - Blue checkmark overlay if already in timeline
- **Grouping:** Cards grouped by stage with sticky headers: `🥕 Prep → 🔥 Cook → 🍽 Plate`

**Sorting:** Default by source timestamp. Options: quality (desc), duration, alphabetical.

## Preview

**Hover:** Scrubable thumbnail (mousemove across card = scrub through clip, like YouTube).

**Click:** Inline expanded preview — card expands to panel width, plays clip with audio. Shows full metadata: timestamp, duration, quality breakdown (sharpness/exposure/framing), auto-tags. Two action buttons: **Insert** and **Close**.

## Insertion Methods

1. **Drag & drop** — Drag card directly onto timeline. Drop zone highlights valid insertion points between existing clips. Snaps to nearest cut point.

2. **Insert button** — Click "Insert" from preview. Opens placement popover: "After [current clip name]" with dropdown to pick position. Confirms with one click.

3. **Right-click context menu** — "Insert after current playhead," "Insert at end," "Replace selected clip."

On insert: clip moves from "unused" pool visually (gets blue checkmark), edit plan updates, timeline re-renders. Fully undoable.

## Technical Notes

- Thumbnails/previews pre-generated during ingest pipeline (no on-demand transcoding)
- Virtual scroll on grid — libraries can have 200+ clips
- Search is client-side fuzzy match on label + tags (dataset is small enough)
- Quality score computed from: AI action-detection confidence (40%), blur detection (20%), exposure (20%), framing/rule-of-thirds (20%)

This gives users full visibility into what the AI "saw" while keeping the default experience clean — unused clips are one click away, never in the way.

## deep-6-thumbnails



# Thumbnail Generation System for Videopeen Preview

## Reuse Existing Frames — Don't Re-extract

The pipeline already extracts frames every 2 seconds for AI analysis. **Reuse these.** No separate FFmpeg pass needed.

**Frame selection strategy:** Pick the frame closest to the clip's 33% mark (not midpoint — cooking clips often start with setup and end with plating; the action is in the first third). If we have scene-change detection scores from AI analysis, prefer the frame with highest visual complexity within the clip's range. Fallback: first extracted frame after clip start + 1 second.

## When: During Clip Detection, Not After

Thumbnails generate **as a side-effect of the existing frame extraction step**. When the AI identifies clip boundaries, we already have the frames in memory/storage. The clip detection output includes `selectedFrameIndex` — we just resize that frame.

Pipeline: `Upload → Frame Extraction (2s intervals) → AI Analysis → Clip Detection + Thumbnail Selection → Store`

Zero additional processing time added to the critical path.

## Format & Resolution

- **Size:** 320×180 (16:9) — sharp enough to identify, small enough to be fast
- **Format:** WebP, quality 75 — ~8-15KB per thumbnail vs ~30KB for JPEG
- **Fallback:** JPEG for Safari <14 (negligible now, drop soon)

For a typical 10-minute video with ~15 clips: **~150KB total**. Trivial.

## Sprite Sheets vs Individual Images

**Individual images.** Here's why:

- Clips get reordered/deleted — sprite sheets require regeneration or wasteful partial loads
- 15 images × 12KB = 180KB, loaded in parallel via HTTP/2 multiplexing
- Sprite sheets save on requests but we're already on HTTP/2+; the complexity isn't worth it
- Individual images enable per-clip lazy loading

## Serving & Performance

```
Storage: S3 → CloudFront CDN
Path: /thumbnails/{videoId}/{clipId}.webp
Cache: immutable, 1 year (clip IDs are content-addressed)
```

**Client-side:**
- `loading="lazy"` on all thumbnails below the fold
- Inline the first 3 thumbnails as base64 in the initial API response (~36KB) for instant render
- `<img>` with `aspect-ratio: 16/9` to prevent layout shift
- Blurhash placeholder (4×3, ~20 bytes per clip) embedded in clip metadata

## Storage Cost

15 thumbnails × 12KB × 100K videos/month = **~18GB/month**. Negligible. No cleanup needed — thumbnails die with video deletion.

## API Shape

```json
{
  "clipId": "c_abc123",
  "thumbnail": {
    "url": "https://cdn.videopeen.com/thumb/v_xyz/c_abc123.webp",
    "blurhash": "LEHV6nWB2yk8",
    "width": 320,
    "height": 180
  }
}
```

**The key insight:** This isn't a new system — it's a ~50-line addition to the existing frame extraction step, plus a resize call. Ship it in a day.

## deep-7-drag-drop



# Drag-and-Drop Reorder System — Videopeen

## Library: `@dnd-kit/core` + `@dnd-kit/sortable`

React-beautiful-dnd is unmaintained. dnd-kit is the production standard: tree-shakeable (~12KB), built-in keyboard/screen-reader support, first-class touch sensors, and composition-based architecture.

## Architecture

```
ClipTimeline (DndContext + SortableContext)
├── SortableClip[] (useSortable hook per clip)
│   ├── ClipThumbnail
│   ├── DragHandle
│   └── DurationBadge
└── DragOverlay (portal-rendered ghost)
```

**State flow:** Zustand store holds `clipIds: string[]`. On `onDragEnd`, dispatch `reorderClips(activeId, overId)` which calls `arrayMove()`. The store update is the source of truth — React re-renders the sorted list.

## Drag UX

- **DragOverlay** renders a styled clone (scaled 1.03×, `box-shadow: 0 12px 24px rgba(0,0,0,0.15)`, 2° rotation) — detached from layout so no jank.
- **Placeholder:** The origin slot collapses with `height: 0` + CSS transition (200ms ease). Adjacent clips animate into place via `transform` (handled by `SortableContext` + `CSS.Transition`).
- **Drop indicator:** A 2px accent-color bar appears between clips at the projected drop position using `closestCenter` collision detection.
- **Modifiers:** `restrictToParentElement` + `restrictToHorizontalAxis` for horizontal timeline.

## Sensors

```ts
const sensors = useSensors(
  useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  useSensor(TouchSensor, { activationConstraint: { delay: 150, tolerance: 5 } }),
  useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
);
```

Touch delay prevents conflict with scroll. Pointer distance prevents accidental drags on click.

## Performance (20-30 clips)

- Each `SortableClip` wrapped in `React.memo` — only the moved clips re-render.
- Thumbnails lazy-loaded via `IntersectionObserver`. DragOverlay uses a pre-cached thumbnail.
- `clipIds` array is the minimal reactive state — no deep object comparisons.

## Undo/Redo Integration

```ts
// In Zustand store with temporal middleware (zundo)
reorderClips: (activeId, overId) => {
  const oldIndex = state.clipIds.indexOf(activeId);
  const newIndex = state.clipIds.indexOf(overId);
  set({ clipIds: arrayMove(state.clipIds, oldIndex, newIndex) });
  // zundo automatically snapshots previous state
}
```

`Cmd+Z` / `Cmd+Shift+Z` bound globally, calls `temporal.undo()` / `temporal.redo()`.

## Optimistic Updates

Reorder is local-first. The UI updates instantly. A debounced `saveOrder()` (500ms) PATCHes the backend with the new `clipIds` array. On failure, `temporal.undo()` + toast error. No loading spinners for drag operations ever.

## Accessibility

dnd-kit provides live `aria-describedby` announcements out of the box: *"Picked up clip 3 of 8. Use arrow keys to reorder."* Custom `announcements` config for cooking context: *"Moved 'Dice Onions' to position 4."*

## deep-8-render-pipeline



# Videopeen Render Pipeline

## 1. Normalization Pass (parallel, per-clip)

```bash
ffmpeg -i clip_N.mov -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:-1:-1,fps=30" \
  -c:v libx264 -profile:v high -crf 18 -preset fast -g 30 -keyint_min 30 \
  -c:a aac -ar 48000 -ac 2 -b:a 192k \
  -movflags +faststart -y normalized/clip_N.mp4
```

Fixed GOP (`-g 30 -keyint_min 30`) ensures every clip starts/ends on a keyframe. Uniform resolution, framerate, sample rate eliminates concat issues. Run all clips in parallel via worker pool.

## 2. Concat + Transitions

**No transitions (fast path):** Use concat demuxer — zero re-encode:
```bash
# filelist.txt generated from edit plan JSON
file 'normalized/clip_0.mp4'
file 'normalized/clip_1.mp4'
...
ffmpeg -f concat -safe 0 -i filelist.txt -c copy -movflags +faststart output.mp4
```

**With crossfades:** Build a complex filtergraph dynamically from the edit plan:
```bash
ffmpeg -i clip_0.mp4 -i clip_1.mp4 -i clip_2.mp4 \
  -filter_complex "
    [0:v][1:v]xfade=transition=fade:duration=0.5:offset=4.5[v01];
    [v01][2:v]xfade=transition=fade:duration=0.5:offset=9.0[vout];
    [0:a][1:a]acrossfade=d=0.5:c1=tri:c2=tri[a01];
    [a01][2:a]acrossfade=d=0.5:c1=tri:c2=tri[aout]" \
  -map "[vout]" -map "[aout]" \
  -c:v libx264 -profile:v baseline -level 3.1 -crf 23 -preset medium \
  -c:a aac -b:a 128k -movflags +faststart output.mp4
```

Offsets are computed by walking the edit plan: `offset_N = sum(clip_durations[0..N]) - sum(crossfade_durations[0..N])`.

## 3. Quality Presets

| Preset | CRF | Profile | Preset | Resolution |
|--------|-----|---------|--------|------------|
| draft  | 28  | baseline| ultrafast | 720p |
| standard | 23 | baseline | medium | 1080p |
| high   | 18  | high    | slow   | 1080p |

## 4. Progress Reporting

```bash
ffmpeg ... -progress pipe:1
```

Parse `out_time_us` from stdout, divide by total expected duration → percentage. Push via WebSocket to client.

## 5. Error Recovery

- Each normalize job is idempotent — retry up to 3x on failure.
- Final render: if ffmpeg exits non-zero, check `normalized/` cache (still valid), retry render only.
- Store edit plan JSON + normalized clips as the "checkpoint" — user can re-trigger render without re-normalizing.
- On OOM/timeout: fall back to `draft` preset automatically, notify user.

## 6. Edit Plan → ffmpeg (pseudocode)

```python
def build_render(plan: EditPlan) -> str:
    clips = [normalize(c) for c in plan.clips]  # parallel
    if not plan.transitions:
        return concat_demuxer(clips)
    inputs = " ".join(f"-i {c}" for c in clips)
    vchain, achain, offset = [], [], 0.0
    for i in range(len(clips) - 1):
        dur = plan.transitions[i].duration
        offset += clips[i].duration - dur
        # chain xfade/acrossfade filters
    return f"ffmpeg {inputs} -filter_complex '...' {PRESET[plan.quality]} output.mp4"
```

**Key decisions:** Normalize-first eliminates 90% of edge cases. Concat demuxer for transition-free renders is near-instant. Baseline H.264 + `faststart` ensures universal browser playback.

## deep-9-smart-features



# Preview Before Render — Smart Review Screen

## Timeline Intelligence Layer

The timeline uses a **four-color stage system**: blue (prep), orange (cook), green (plate), gold (serve). Each clip sits as a colored block, giving instant visual comprehension of edit flow. A thin gradient bridge connects clips where the AI detected a natural transition.

## Core Smart Features

**1. Sequence Validator**
A passive rule engine checks cooking logic in real-time. If plating appears before cooking, a gentle amber bar appears above the offending clips: *"Plating shown before cooking — intentional?"* with **Fix** and **Dismiss** buttons. Fix triggers the Suggested Reorder engine. No modal interruptions.

**2. AI Confidence Indicators**
Each clip shows a subtle confidence dot (green/yellow/red) in its corner. Hover reveals a tooltip: *"Matched 'dice onions' with 94% confidence. Selected over 2 alternatives — best lighting, steadiest frame."* This explains the AI's reasoning without cluttering the default view. Yellow/red clips get a small "swap" icon to browse alternatives inline.

**3. Coverage Map**
A collapsible sidebar panel lists every recipe step extracted from the source. Covered steps show a checkmark; missing steps pulse softly in red. Users see at a glance: *"8/10 steps covered — missing: season the steak, rest before slicing."* Each missing step offers **Find Clip** (AI searches raw footage) or **Mark Optional**.

**4. Duration Gauge**
A minimal bar beneath the timeline shows current total vs. target duration. The bar is segmented by stage color, so users immediately see *which stage* is too long. Dragging clip edges updates the gauge live.

**5. Duplicate Detection**
When the AI detects two clips showing the same action (e.g., two "add salt" moments), it links them with a dotted connector and labels one *"possible duplicate."* One click keeps the better-scored clip.

**6. Suggested Reorder**
A single button that proposes an optimized sequence based on recipe logic, stage flow, and pacing. Changes preview as a ghost overlay on the timeline — accept, reject, or cherry-pick individual moves.

## Design Principles

- **Progressive disclosure**: Default view is clean — colored blocks, duration gauge, confidence dots. Details emerge on hover/click.
- **Non-blocking warnings**: Alerts are inline banners, never modals.
- **Undo everything**: Every AI suggestion is reversible in one click.

Smart enough to catch real problems. Quiet enough to stay out of the way.

## deep-10-state-machine



# Videopeen State Machine & Flow

## States & Transitions

```
IDLE → UPLOADING → ANALYZING → REVIEW → EDITING → RENDERING → COMPLETED
                                                       ↓
         Any state → ERROR → (retry to previous state)
                             EDITING ← RENDER_FAILED
                             EDITING ← COMPLETED (re-edit)
```

**States:**

| State | UI | WebSocket Events |
|---|---|---|
| `IDLE` | Upload dropzone | — |
| `UPLOADING` | Progress bar, chunked upload % | `upload:progress {%}` |
| `ANALYZING` | Skeleton UI + phase text ("Detecting scenes…", "Identifying ingredients…") | `analyze:phase`, `analyze:progress` |
| `REVIEW` | Timeline with AI-proposed clips, suggested cuts, music. Read-only preview. | `review:ready {editPlan}` |
| `EDITING` | Full timeline editor — drag/reorder, trim, delete, add text/transitions | `edit:autosave` |
| `RENDERING` | Progress bar, ETA, locked timeline | `render:progress {%, eta}` |
| `COMPLETED` | Video player + Download/Share buttons | `render:done {url}` |
| `ERROR` | Error banner with retry/back action | `error {code, retryable, fallbackState}` |

## Allowed Transitions

```typescript
const TRANSITIONS = {
  IDLE:        ['UPLOADING'],
  UPLOADING:   ['ANALYZING', 'ERROR'],
  ANALYZING:   ['REVIEW', 'ERROR'],
  REVIEW:      ['EDITING'],           // user confirms or modifies
  EDITING:     ['RENDERING', 'EDITING'], // self-loop = autosave
  RENDERING:   ['COMPLETED', 'ERROR'],
  COMPLETED:   ['EDITING'],           // re-edit flow
  ERROR:       ['UPLOADING', 'ANALYZING', 'RENDERING', 'EDITING'], // context-dependent retry
};
```

## Auto-Save & Session Recovery

- **EDITING** state: debounced autosave every 5s to `project.draft` (server-side). Each save bumps a `version` counter.
- On reconnect/page load: fetch `GET /projects/:id` → server returns `{state, draft, version}` → UI hydrates directly into correct state.
- WebSocket reconnect: client sends `{projectId, lastEventId}` → server replays missed events (event sourcing).

## Edge Cases

- **Leave mid-upload:** Resumable uploads via `tus` protocol. Returns to same byte offset.
- **Leave mid-analysis:** Server continues processing. User returns to REVIEW if done, ANALYZING if not.
- **Render fails:** Transitions to `ERROR` with `fallbackState: 'EDITING'`. User edits and re-queues.
- **Re-edit after complete:** `COMPLETED → EDITING` clones the edit plan. Original render URL preserved.
- **Concurrent tabs:** Optimistic locking via `version`. Second tab gets `409 Conflict` on save → "Newer version exists, reload?"
- **Upload too large / corrupt:** `ERROR` with `retryable: true`, fallback to `IDLE`.
- **WebSocket disconnect mid-render:** Client polls `GET /projects/:id/status` as fallback (30s interval). Reconnects resume event stream.

## Server-Side State Enforcement

State lives in DB. All transitions validated server-side — client requests transition, server accepts/rejects. Prevents impossible states regardless of client bugs.

