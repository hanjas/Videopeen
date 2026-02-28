# Testing Checklist: Task 001 - Vertical Export

**Feature:** Aspect ratio selection (9:16, 1:1, 16:9)  
**Implementation Date:** 2026-02-28  
**Status:** ⏳ READY FOR TESTING

---

## Pre-Test Setup

1. **Ensure MongoDB is running:**
   ```bash
   docker start videopeen-mongo
   ```

2. **Start backend:**
   ```bash
   cd backend
   source .venv/bin/activate
   uvicorn app.main:app --port 8000 --reload
   ```

3. **Start frontend:**
   ```bash
   cd frontend
   npm run dev
   ```

4. **Test videos needed:**
   - Landscape video (e.g., `~/Downloads/IMG_2748.MOV`)
   - Portrait video (if available)

---

## Test Cases

### ✅ Test 1: Create 9:16 Vertical Project

**Goal:** Verify vertical export works end-to-end

**Steps:**
1. Go to http://localhost:3000/dashboard
2. Click "+ New Project"
3. Enter project name: "Test 9:16 Vertical"
4. Select **📱 9:16** aspect ratio
5. Upload a landscape video (e.g., IMG_2748.MOV)
6. Click "Generate Video"
7. Wait for processing to complete

**Expected Results:**
- [ ] Project creates successfully
- [ ] Pipeline runs without errors
- [ ] Proxy preview shows vertical video (tall/portrait orientation)
- [ ] Final HD render is 1080x1920 (vertical)
- [ ] Video plays correctly in browser
- [ ] Export button downloads vertical video

**Check with ffprobe:**
```bash
ffprobe outputs/{project_id}_final.mp4 2>&1 | grep -E "(Video|Stream|resolution)"
```
Should show: `1920x1080` → `1080x1920` (width x height)

---

### ✅ Test 2: Create 1:1 Square Project

**Goal:** Verify square export works

**Steps:**
1. Create new project: "Test 1:1 Square"
2. Select **⬜ 1:1** aspect ratio
3. Upload same video
4. Generate and wait

**Expected Results:**
- [ ] Proxy preview is square
- [ ] Final HD render is 1080x1080 (square)
- [ ] Video is perfectly square (no letterboxing)
- [ ] Export downloads square video

**Check with ffprobe:**
```bash
ffprobe outputs/{project_id}_final.mp4 2>&1 | grep -E "1080x1080"
```

---

### ✅ Test 3: Create 16:9 Landscape Project (Regression Test)

**Goal:** Verify default behavior still works

**Steps:**
1. Create new project: "Test 16:9 Landscape"
2. Select **🖥 16:9** aspect ratio (default)
3. Upload video
4. Generate and wait

**Expected Results:**
- [ ] Works exactly like before (no changes to existing workflow)
- [ ] Proxy preview is landscape
- [ ] Final HD render is 1920x1080 (landscape)
- [ ] Video looks correct

**Check with ffprobe:**
```bash
ffprobe outputs/{project_id}_final.mp4 2>&1 | grep -E "1920x1080"
```

---

### ✅ Test 4: UI Checks

**Project Creation Modal:**
- [ ] Aspect ratio selector shows 3 options with icons
- [ ] Default is 16:9 (landscape)
- [ ] Selecting a format shows descriptive text below
- [ ] Selected format is highlighted in orange

**Project Page:**
- [ ] Video player shows correct aspect ratio
- [ ] Export format selector shows above download button
- [ ] Current format is marked with green checkmark
- [ ] Selecting different format shows "coming soon" message

---

### ✅ Test 5: Conversational Editing with Aspect Ratio

**Goal:** Verify proxy re-rendering respects aspect ratio

**Steps:**
1. Create a 9:16 project and let it complete
2. Use conversational edit: "Make it 30 seconds"
3. Wait for proxy preview to update

**Expected Results:**
- [ ] New proxy preview is still vertical (9:16)
- [ ] HD re-render completes successfully
- [ ] Final video is still 1080x1920

---

### ✅ Test 6: Portrait Source Video (if available)

**Goal:** Verify crop logic handles portrait sources correctly

**Steps:**
1. If you have a portrait source video (shot vertically):
2. Create 9:16 project with portrait source
3. Generate

**Expected Results:**
- [ ] No excessive cropping (source is already vertical)
- [ ] Output is clean 1080x1920
- [ ] No black bars or distortion

---

## Error Cases to Check

### ❌ Invalid Aspect Ratio

**Manual API Test:**
```bash
curl -X POST http://localhost:8000/api/projects \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Invalid", "aspect_ratio": "21:9"}'
```

**Expected:** Should accept any string (no validation currently - could add later)

---

## Performance Checks

### 🚀 Proxy Rendering Speed

**Check backend logs for timing:**
```
Pre-rendering X proxy clips for project {id} (max 3 concurrent)
Pre-rendered X/Y proxy clips for project {id}
```

**Expected:**
- [ ] Proxy rendering completes in reasonable time (< 30s for 10 clips)
- [ ] No OOM crashes

### 🚀 Fast Concat Speed

**Check logs:**
```
Fast concat X proxy clips → {path} (project {id})
Fast concat complete: {path} ({size} KB, {n} clips)
```

**Expected:**
- [ ] Concat completes in 2-5 seconds
- [ ] Proxy preview available almost instantly

---

## Visual Quality Checks

### 📐 Crop Quality

**For 9:16 from landscape source:**
- [ ] Important content is centered (not cut off)
- [ ] Food/action is visible (not cropped out)
- [ ] No weird aspect ratio distortion

**For 1:1 from landscape source:**
- [ ] Square crop is centered
- [ ] Main subject is visible
- [ ] Looks balanced (not awkward)

---

## Rollback Plan (If Tests Fail)

If critical bugs found:

1. **Revert commits:**
   ```bash
   git log --oneline  # find commit hash
   git revert {hash}
   ```

2. **Or disable feature temporarily:**
   - Remove aspect ratio selector from frontend
   - Set default to "16:9" everywhere
   - Add validation to reject non-16:9 for now

3. **Document issues** in AGENT-STATE.md under "Blockers"

---

## Success Criteria

✅ **All tests pass:**
- 9:16 vertical export works
- 1:1 square export works
- 16:9 landscape still works (no regression)
- Proxy system respects aspect ratio
- No crashes or errors
- UI is intuitive and works as expected

✅ **Ready to move to Task 002** (Audio Preservation)

---

## Notes for Tester

- **ffprobe command** to check video dimensions:
  ```bash
  ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=s=x:p=0 outputs/{project_id}_final.mp4
  ```

- **Expected output formats:**
  - 9:16 → `1080x1920`
  - 1:1 → `1080x1080`
  - 16:9 → `1920x1080`

- **If you see reversed dimensions** (1920x1080 instead of 1080x1920):
  - Check if rotation metadata is being applied
  - Might need to add `-noautorotate` or handle rotation differently

- **Backend logs location:**
  - Terminal where you ran `uvicorn` (watch for errors)
  - Can pipe to file: `uvicorn app.main:app --port 8000 --reload 2>&1 | tee /tmp/videopeen-test.log`
