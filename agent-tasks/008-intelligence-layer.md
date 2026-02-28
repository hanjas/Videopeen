# Task 008: Intelligence Layer — Make AI Visible

**Priority:** HIGH
**Effort:** 3-5 days
**Depends on:** Task 007 (quick wins should be done first)

## Context
Users expect an "intelligent" platform to SHOW its intelligence. Our backend already generates AI insights (edit plans, clip descriptions, action detection) but the frontend hides them. This task surfaces that intelligence.

## Read First
- `videopeen/UI-REVIEW.md` — see "What Users Expect" section
- `videopeen/ui-review-screenshots/` — reference screenshots
- Backend API: check what data is already returned in project/edit responses

## Checklist

### 1. "Your Edit is Ready" Summary Card (1 day)
After pipeline completes, show an intelligence summary card before the video player:
- [x] Create `EditSummaryCard` component
- [x] Show: total footage analyzed, clips extracted, hero moments found
- [x] Show: recipe/dish identified (from AI analysis)
- [x] Show: story structure built (Prep → Assembly → Cook → Reveal)
- [x] Show: best moment highlight ("The chocolate pour at 3:08 is your hook")
- [x] Dismissible — once dismissed, shows compact version in header
- [x] Data source: use existing `edit_plan` response from backend

### 2. Clip Tags / Labels (1 day)
Add visual tags to clips in both editor timeline and Review & Arrange:
- [x] Parse clip descriptions to auto-assign tags
- [x] Tag types: 🔪 Prep, 🍳 Cook, ✨ Hero, ⚡ Action, 🎬 Reveal, 📸 Beauty Shot
- [x] Show as small colored pills on clip cards
- [x] Highlight hero/key moments with a star or glow effect
- [x] Backend may need a small update to return structured tags (or do it frontend-side from descriptions)

### 3. AI Notes on Editor Page (0.5 day)
- [x] The AI Notes section currently only exists on Review & Arrange page
- [x] Add a collapsible "🤖 AI Analysis" section on the main editor page
- [x] Show structured AI notes: Recipe, Flow, Key Moments
- [x] Make it always visible (not behind a click)

### 4. Suggested Prompt Chips (0.5 day)
Below the chat input, add clickable suggestion chips:
- [x] "Remove blurry clips"
- [x] "Make it 30 seconds"
- [x] "Speed up prep section"
- [x] "Add the close-up shot"
- [x] "Remove idle moments"
- [x] Clicking a chip fills the input and auto-sends
- [x] Context-aware: if video is >45s, suggest "Make it shorter"

### 5. Simplify New Project Modal (0.5 day)
- [x] Remove transition style, transition duration, format selection from modal
- [x] Keep only: Project Name + File Upload + Create button (+ Format selector)
- [x] Let AI pick defaults (fade transition, 0.5s, 9:16 for cooking)
- [x] Move format/transition options to editor page (post-processing settings)
- [x] Add text: "AI will analyze your footage and create the best edit"

## Testing
- [ ] Upload new project — verify simplified modal
- [ ] After pipeline completes — verify summary card appears
- [ ] Check clip tags on editor timeline
- [ ] Check clip tags on Review & Arrange page (tags may not show there yet - that page uses different data)
- [ ] Check AI Notes visible on editor page and is collapsible
- [ ] Check prompt chips appear, are clickable, and auto-submit
- [ ] Verify Edit Summary Card can be dismissed and minimized
- [ ] Verify no backend errors
- [ ] Test with different video durations to see context-aware prompt chips

## Files Likely Involved
- `frontend/app/dashboard/project/[id]/page.tsx` — editor page
- `frontend/app/dashboard/project/[id]/review/page.tsx` — review page
- `frontend/components/` — new components (EditSummaryCard, ClipTag, PromptChips)
- `frontend/app/dashboard/page.tsx` — new project modal
- Backend: check `/api/projects/{id}` response for available AI data
