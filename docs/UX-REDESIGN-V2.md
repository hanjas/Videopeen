# Videopeen UX Redesign V2 — Expert Synthesis

**Date:** 2026-02-22
**Based on:** 10 expert agent reviews (UX, mobile, psychology, growth, AI architect, CapCut designer, simplifier, creator, video editor, competitive analyst)

---

## Core Insight

**We're building an AI-enhanced video editor, not a manual editor with AI suggestions.** Users should never have to manually drag-drop 18 clips. The AI is the editor; the user is the director.

---

## New Flow (3 clicks to export)

```
Upload → AI Processes → "Your video is ready!" (auto-play preview) → Export
                                                    ↓ (optional)
                                              "Adjust" → Conversational Editor
```

### Old Flow (kill this)
Upload → Name Project → Wait → See 18 clip cards → Drag to reorder → Save → Render → Wait

### New Flow
Upload → Wait → Full video preview auto-plays → Export (or "Adjust" for tweaks)

---

## Key Design Decisions

### 1. Preview First, Always
- After AI processing, show the **assembled video playing automatically**
- NOT clip cards. The finished video.
- Two buttons: **"Export"** (primary, big) and **"Adjust"** (secondary, subtle link)
- 80%+ users should just hit Export

### 2. Conversational Editing (NOT drag-drop)
- Edits happen via **text input** (future: voice)
- Examples:
  - "Remove the second chopping clip"
  - "Make it more fast-paced"
  - "Swap the intro for the overhead shot"
  - "Cut the part where I'm just waiting for water to boil"
  - "Make this a 60-second TikTok"
- Claude interprets intent and re-edits
- This is the MOAT — cooking creators talk about food, not timecodes
- **NO manual drag-drop as primary interaction**

### 3. Pages: 6 → 3
- **Landing** — Before/after video demo, sign up
- **Dashboard** — Projects list + "New Project" button (no separate New page)
- **Editor** — Preview + conversational adjust + export (merges old Project View + Review + Arrange)
- **Settings** → Slide-out panel from anywhere, not a page
- **New Project** → Modal/inline on Dashboard, not a page

### 4. AI Confidence-Based Decisions
- AI assigns confidence to each edit decision
- High confidence (>85%): auto-locked, not shown to user
- Only surface 2-3 uncertain decisions as simple A/B choices:
  - "Close-up or wide shot for plating?"
  - "This clip seems optional — keep it?"
- NOT 18 clips to review

### 5. Cooking Stages (Visual Grouping)
- When "Adjust" is opened, show clips grouped by stage:
  - **Setup** (intro, ingredients)
  - **Prep** (chopping, measuring)
  - **Cook** (heat, transformation, sizzle)
  - **Assembly** (plating, layering)
  - **Money Shot** (hero beauty shot, first bite, cross-section)
- Pacing bar shows proportional duration per stage
- Money shot auto-detected, highlighted with gold border

### 6. Clip Scores
- Each clip gets an AI quality/relevance score (like Opus Clip's virality score)
- Helps users quickly spot weak suggestions
- Accept/reject per item, not rebuild

### 7. Auto Everything
- **Auto-save** always (no save button)
- **Auto-name** projects ("Pasta Video - Feb 22"), rename later
- **Auto-render in background** while user previews (if they change nothing, video is already done)

### 8. Mobile-First Design
- Vertical stack, full-width cards (not horizontal strip)
- Swipe left to remove, long-press to reorder
- Bottom action bar in thumb zone: Preview, Add Clip, Done
- Show top 8-10 clips by default, collapse rest under "More clips"

### 9. Duration Control via Conversation
- "Make this a 90-second TikTok"
- "Make a 30-second Instagram Reel version"
- "Make a 4-minute YouTube version"
- AI re-selects and trims clips to hit target
- Future: generate multiple format variations automatically

### 10. BYOK Strategy
- DON'T lead with "bring your API key" — kills conversion
- Lead with Pro plan ($25/mo) or free trial credits (2-3 free videos)
- BYOK hidden behind Advanced/Developer settings
- Normal users should never see "API key"

---

## Quick Wins (Ship First)

1. Preview-first flow (kill mandatory Review & Arrange)
2. Text-based conversational editing
3. Auto-name projects
4. Auto-save
5. Merge pages (6 → 3)

## Phase 2

6. AI confidence scores + A/B choices
7. Cooking stage grouping
8. Background pre-render
9. Mobile gestures
10. Duration targeting via conversation

## Phase 3

11. Voice editing ("Hey Videopeen, cut the boring part")
12. Multi-format export (9:16, 1:1, 16:9 from one edit)
13. Auto-captions
14. CapCut project file export (bridge to finishing tools)
15. Template system

---

## Competitive Reference

| Tool | Pattern | Steal This |
|------|---------|-----------|
| Opus Clip | Ranked cards with virality scores | Confidence/quality scores per clip |
| Descript | Edit-in-transcript, track changes | Accept/reject actions on a list |
| CapCut AI | One-tap template, preview-first | Preview before any editing |
| Runway/Pika | 2-4 variations to pick from | A/B choices for uncertain edits |
| Canva | Templates ship "done" | Default = finished, edit = optional |

---

## The Principle

> "Users don't want control. They want the feeling they could control it if needed."
> — A locked door you have the key to feels safe. A room with 18 unlocked doors feels chaotic.

> "Stop treating the AI as a prep cook who hands ingredients to the chef. Make it the chef who asks 'taste this — more salt?'"

---

## Creator Feedback (Simulated Expert)

- Speed is impressive (15 min vs 45 min manual)
- AI notes and edit strategy are cool
- Would use for first rough assembly — absolute yes
- Won't switch from CapCut until: auto-captions, music, vertical format, transitions, intro/outro templates
- **Killer feature request: Export timeline importable into CapCut**
- Duration targeting per platform is "everything"
