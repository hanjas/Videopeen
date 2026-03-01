# Task 012: Bug Fixes

## Bugs to Fix

### 1. Orphaned edit_plans cleanup on project delete
**File:** `backend/app/routers/projects.py` — `delete_project` function (~line 103)
**Problem:** When deleting a project, the `edit_plans` collection is not cleaned up.
**Fix:** Add `await db.edit_plans.delete_many({"project_id": project_id})` alongside the other collection cleanups.

### 2. Missing favicon
**File:** `frontend/app/` (Next.js app directory)
**Problem:** 404 on `/favicon.ico`
**Fix:** Create a simple favicon. Use Next.js metadata approach — add a `favicon.ico` or use `icon.tsx` route handler. Simplest: create `frontend/app/icon.tsx` that generates a simple orange cooking-themed icon (like a 🍳 or just "VP" text on orange background). Or just create `frontend/public/favicon.ico` — but check if `public/` dir exists first.

### 3. React key warnings in ProjectPage
**File:** `frontend/app/dashboard/project/[id]/page.tsx`
**Problem:** Missing unique "key" prop warnings. Check ALL `.map()` calls and ensure each has a unique key. The ones at the bottom timeline (~line 1217) already use `key={clipId || \`clip-${idx}\`}` which is fine. Check the ones around line 810, 884, 953, 1141, 1289, 1341, 1431, 1456 for missing or non-unique keys.

### 4. EditSummaryCard setState during render
**File:** `frontend/components/EditSummaryCard.tsx`
**Problem:** "Cannot update a component while rendering a different component" — this happens when `parseNotes()` or `findHeroMoment()` are called during render AND somehow trigger state updates.
**Analysis:** Looking at the code, `parseNotes()` and `findHeroMoment()` are pure functions called during render — they don't setState. The issue is likely that `insights` computation triggers a re-render of a parent. Actually, this component looks clean. The error might come from the PARENT component passing props that change during render. Check if `EditSummaryCard` is used inside a `.map()` or conditional that causes issues. The actual fix may need to be in the parent `ProjectPage` where EditSummaryCard is rendered — wrap any derived state in useMemo or useEffect.
**Action:** Find where EditSummaryCard is used in ProjectPage, check if any props passed to it cause state updates during render. Wrap expensive computations in useMemo.

### 5. CORS — add localhost:3002 to allowed origins
**File:** `backend/app/main.py` (line ~25) and `backend/app/config.py`
**Problem:** CORS errors when frontend runs on port 3002
**Fix:** Add `"http://localhost:3002"` to the `allow_origins` list in `main.py`. Better yet, make it permissive for local dev: add all common localhost ports or use a wildcard pattern for localhost.

### 6. 416 Range Not Satisfiable on video
**Problem:** Browser gets 416 when trying to load video. This happens when the video file is being written/doesn't exist yet, or when the static file server doesn't handle Range requests properly for incomplete files.
**Fix:** This is likely a timing issue — video not ready when player tries to load. In the frontend, only show the video player when the project status is "completed" AND the output_path is set. Check ProjectPage video player section and add a guard.

## Environment
- Project root: `~/.openclaw/workspace/videopeen/`
- Frontend: `frontend/` (Next.js 14, TypeScript)
- Backend: `backend/` (FastAPI, Python)
- Do NOT restart servers — just make code changes and commit
- Run `cd frontend && npx next build` to verify no build errors before committing

## Commit
After all fixes, commit with message: "fix: resolve runtime bugs (CORS, keys, favicon, edit_plans cleanup, 416)"
