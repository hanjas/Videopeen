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
- [ ] Create `EditSummaryCard` component
- [ ] Show: total footage analyzed, clips extracted, hero moments found
- [ ] Show: recipe/dish identified (from AI analysis)
- [ ] Show: story structure built (Prep → Assembly → Cook → Reveal)
- [ ] Show: best moment highlight ("The chocolate pour at 3:08 is your hook")
- [ ] Dismissible — once dismissed, shows compact version in header
- [ ] Data source: use existing `edit_plan` response from backend

### 2. Clip Tags / Labels (1 day)
Add visual tags to clips in both editor timeline and Review & Arrange:
- [ ] Parse clip descriptions to auto-assign tags
- [ ] Tag types: 🔪 Prep, 🍳 Cook, ✨ Hero, ⚡ Action, 🎬 Reveal, 📸 Beauty Shot
- [ ] Show as small colored pills on clip cards
- [ ] Highlight hero/key moments with a star or glow effect
- [ ] Backend may need a small update to return structured tags (or do it frontend-side from descriptions)

### 3. AI Notes on Editor Page (0.5 day)
- [ ] The AI Notes section currently only exists on Review & Arrange page
- [ ] Add a collapsible "🤖 AI Analysis" section on the main editor page
- [ ] Show structured AI notes: Recipe, Flow, Key Moments
- [ ] Make it always visible (not behind a click)

### 4. Suggested Prompt Chips (0.5 day)
Below the chat input, add clickable suggestion chips:
- [ ] "Remove blurry clips"
- [ ] "Make it 30 seconds"
- [ ] "Speed up prep section"
- [ ] "Add the close-up shot"
- [ ] "Remove idle moments"
- [ ] Clicking a chip fills the input and auto-sends
- [ ] Context-aware: if video is >45s, suggest "Make it shorter"

### 5. Simplify New Project Modal (0.5 day)
- [ ] Remove transition style, transition duration, format selection from modal
- [ ] Keep only: Project Name + File Upload + Create button
- [ ] Let AI pick defaults (fade transition, 0.5s, 9:16 for cooking)
- [ ] Move format/transition options to editor page (post-processing settings)
- [ ] Add text: "AI will analyze your footage and create the best edit"

## Testing
- [ ] Upload new project — verify simplified modal
- [ ] After pipeline completes — verify summary card appears
- [ ] Check clip tags on editor timeline
- [ ] Check clip tags on Review & Arrange page
- [ ] Check AI Notes visible on editor page
- [ ] Check prompt chips appear and work
- [ ] Verify no backend errors

## Files Likely Involved
- `frontend/app/dashboard/project/[id]/page.tsx` — editor page
- `frontend/app/dashboard/project/[id]/review/page.tsx` — review page
- `frontend/components/` — new components (EditSummaryCard, ClipTag, PromptChips)
- `frontend/app/dashboard/page.tsx` — new project modal
- Backend: check `/api/projects/{id}` response for available AI data
