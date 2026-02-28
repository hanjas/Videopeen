# Text Overlays API Testing Guide

Quick guide for manually testing the text overlay endpoints.

## Prerequisites

1. Backend running: `cd backend && uvicorn app.main:app --port 8000 --reload`
2. Have a project with an edit plan (after processing a video)
3. Know your project ID

## API Endpoints

### 1. Get Current Overlays

```bash
curl http://localhost:8000/api/projects/YOUR_PROJECT_ID/edit-plan/overlays
```

**Expected Response:**
```json
{
  "overlays": [],
  "count": 0
}
```

---

### 2. Add Overlays Manually

```bash
curl -X POST http://localhost:8000/api/projects/YOUR_PROJECT_ID/edit-plan/overlays \
  -H "Content-Type: application/json" \
  -d '{
    "overlays": [
      {
        "text": "Step 1: Dice the onions",
        "start_time": 0.0,
        "end_time": 5.0,
        "position": "bottom-center",
        "style": "bold-white",
        "font_size": 48
      },
      {
        "text": "2 cloves garlic, minced",
        "start_time": 10.0,
        "end_time": 14.0,
        "position": "bottom-center",
        "style": "minimal",
        "font_size": 36
      }
    ]
  }'
```

**Expected Response:**
```json
{
  "success": true,
  "overlays": [...],
  "count": 2
}
```

---

### 3. Auto-Generate from Recipe Steps

**First, update project with recipe steps:**

```bash
curl -X PATCH http://localhost:8000/api/projects/YOUR_PROJECT_ID \
  -H "Content-Type: application/json" \
  -d '{
    "instructions": "Dice onions\nHeat oil in pan\nSauté until golden\nAdd garlic\nSeason with salt"
  }'
```

**Then auto-generate overlays:**

```bash
curl -X POST http://localhost:8000/api/projects/YOUR_PROJECT_ID/edit-plan/overlays/auto-generate \
  -H "Content-Type: application/json" \
  -d '{
    "style": "subtitle-bar"
  }'
```

**Expected Response:**
```json
{
  "success": true,
  "overlays": [
    {
      "text": "Step 1: Dice onions",
      "start_time": 0.0,
      "end_time": 4.0,
      "position": "bottom-center",
      "style": "subtitle-bar",
      "font_size": 48
    },
    ...
  ],
  "count": 5,
  "recipe_steps_count": 5
}
```

---

### 4. Render with Overlays

After setting overlays, trigger render:

```bash
curl -X POST http://localhost:8000/api/projects/YOUR_PROJECT_ID/edit-plan/confirm
```

**Watch logs for:**
```
INFO:app.services.render:Stitching 5 clips from 1 sources → ...
INFO:app.services.text_overlay:Applying 5 text overlays to ... → ...
INFO:app.services.render:Render completed for project ...
```

---

## Test Scenarios

### Scenario 1: Single Overlay (Basic)

```bash
curl -X POST http://localhost:8000/api/projects/YOUR_PROJECT_ID/edit-plan/overlays \
  -H "Content-Type: application/json" \
  -d '{
    "overlays": [
      {
        "text": "Hello World!",
        "start_time": 0.0,
        "end_time": 3.0,
        "position": "center",
        "style": "bold-white",
        "font_size": 60
      }
    ]
  }'
```

### Scenario 2: Multiple Overlays (No Overlap)

```bash
curl -X POST http://localhost:8000/api/projects/YOUR_PROJECT_ID/edit-plan/overlays \
  -H "Content-Type: application/json" \
  -d '{
    "overlays": [
      {
        "text": "Intro",
        "start_time": 0.0,
        "end_time": 3.0,
        "position": "top-center",
        "style": "bold-white",
        "font_size": 48
      },
      {
        "text": "Main content",
        "start_time": 5.0,
        "end_time": 10.0,
        "position": "bottom-center",
        "style": "subtitle-bar",
        "font_size": 48
      },
      {
        "text": "Outro",
        "start_time": 12.0,
        "end_time": 15.0,
        "position": "center",
        "style": "minimal",
        "font_size": 36
      }
    ]
  }'
```

### Scenario 3: Test All Positions

```bash
curl -X POST http://localhost:8000/api/projects/YOUR_PROJECT_ID/edit-plan/overlays \
  -H "Content-Type: application/json" \
  -d '{
    "overlays": [
      {
        "text": "Top Left",
        "start_time": 0.0,
        "end_time": 3.0,
        "position": "top-left",
        "style": "bold-white",
        "font_size": 36
      },
      {
        "text": "Top Center",
        "start_time": 3.0,
        "end_time": 6.0,
        "position": "top-center",
        "style": "bold-white",
        "font_size": 36
      },
      {
        "text": "Bottom Center",
        "start_time": 6.0,
        "end_time": 9.0,
        "position": "bottom-center",
        "style": "bold-white",
        "font_size": 36
      },
      {
        "text": "Center",
        "start_time": 9.0,
        "end_time": 12.0,
        "position": "center",
        "style": "bold-white",
        "font_size": 48
      }
    ]
  }'
```

### Scenario 4: Test All Styles

```bash
curl -X POST http://localhost:8000/api/projects/YOUR_PROJECT_ID/edit-plan/overlays \
  -H "Content-Type: application/json" \
  -d '{
    "overlays": [
      {
        "text": "Bold White Style",
        "start_time": 0.0,
        "end_time": 4.0,
        "position": "bottom-center",
        "style": "bold-white",
        "font_size": 48
      },
      {
        "text": "Subtitle Bar Style",
        "start_time": 5.0,
        "end_time": 9.0,
        "position": "bottom-center",
        "style": "subtitle-bar",
        "font_size": 48
      },
      {
        "text": "Minimal Style",
        "start_time": 10.0,
        "end_time": 14.0,
        "position": "bottom-center",
        "style": "minimal",
        "font_size": 48
      }
    ]
  }'
```

### Scenario 5: Special Characters

```bash
curl -X POST http://localhost:8000/api/projects/YOUR_PROJECT_ID/edit-plan/overlays \
  -H "Content-Type: application/json" \
  -d '{
    "overlays": [
      {
        "text": "Step 1: Add 50% milk & 2 eggs",
        "start_time": 0.0,
        "end_time": 5.0,
        "position": "bottom-center",
        "style": "bold-white",
        "font_size": 48
      }
    ]
  }'
```

---

## Validation Tests

### Test: Invalid Time Range (Should Fail)

```bash
curl -X POST http://localhost:8000/api/projects/YOUR_PROJECT_ID/edit-plan/overlays \
  -H "Content-Type: application/json" \
  -d '{
    "overlays": [
      {
        "text": "Invalid",
        "start_time": 10.0,
        "end_time": 5.0,
        "position": "center",
        "style": "bold-white",
        "font_size": 48
      }
    ]
  }'
```

**Expected:** 400 error with message about invalid time range

### Test: Empty Overlays Array (Should Succeed)

```bash
curl -X POST http://localhost:8000/api/projects/YOUR_PROJECT_ID/edit-plan/overlays \
  -H "Content-Type: application/json" \
  -d '{
    "overlays": []
  }'
```

**Expected:** Success, clears all overlays

---

## MongoDB Verification

Check overlays in database:

```bash
# Connect to MongoDB
docker exec -it videopeen-mongo mongosh

# Switch to database
use videopeen_db

# Find edit plan
db.edit_plans.findOne({project_id: "YOUR_PROJECT_ID"}, {text_overlays: 1})
```

**Expected Output:**
```javascript
{
  _id: ObjectId("..."),
  text_overlays: [
    {
      text: "Step 1: Dice onions",
      start_time: 0,
      end_time: 4,
      position: "bottom-center",
      style: "bold-white",
      font_size: 48
    }
  ]
}
```

---

## Troubleshooting

### Overlays not appearing in rendered video

1. Check logs for errors during overlay application
2. Verify overlay times are within video duration
3. Check font file exists: `ls -la /System/Library/Fonts/Helvetica.ttc`
4. Try with simple text first (no special characters)

### Auto-generate returns empty array

1. Verify project has `instructions` or `recipe_details` field
2. Check that instructions contain recipe steps (one per line)
3. Verify edit plan has clips in timeline

### Render fails after adding overlays

1. Check backend logs for ffmpeg error
2. Verify text escaping (quotes, colons)
3. Try removing overlays and re-rendering
4. Check temp file permissions in output directory

---

## Expected Render Log Output

```
INFO:app.services.render:Stitching 5 clips from 1 sources → /path/to/output/project_id_no_overlays.mp4
INFO:app.services.text_overlay:Applying 3 text overlays to /path/to/output/project_id_no_overlays.mp4 → /path/to/output/project_id_final.mp4
INFO:app.services.text_overlay:Successfully applied text overlays: /path/to/output/project_id_final.mp4
INFO:app.services.render:Cleaned up temp file: /path/to/output/project_id_no_overlays.mp4
INFO:app.services.render:Render completed for project project_id → /path/to/output/project_id_final.mp4
```

---

## Next Steps

Once backend testing is complete, implement frontend:
1. Overlay editor UI
2. Overlay list component
3. Auto-generate button
4. Preview integration

**Backend is ready!** 🚀
