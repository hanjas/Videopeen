# 🚀 Quick Start: Test Vertical Export Feature

**30-Second Test** to verify Task 001 implementation

---

## ⚡ Fast Test (5 minutes)

```bash
# 1. Start services
docker start videopeen-mongo
cd backend && source .venv/bin/activate && uvicorn app.main:app --port 8000 --reload &
cd frontend && npm run dev &

# 2. Open browser
open http://localhost:3000/dashboard

# 3. Create test project
# - Click "+ New Project"
# - Select 📱 9:16 (vertical)
# - Upload ~/Downloads/IMG_2748.MOV
# - Click "Generate Video"

# 4. Wait ~5 minutes for processing

# 5. Check output
ffprobe outputs/*_final.mp4 2>&1 | grep "1080x1920"
# Should see: Stream #0:0: Video: ... 1080x1920 ...
```

---

## ✅ Pass Criteria

**If you see:**
- ✅ Video player shows vertical video (tall, not wide)
- ✅ ffprobe shows `1080x1920` dimensions
- ✅ Video downloads and plays on phone correctly
- ✅ No errors in backend logs

**Then:** Task 001 is ✅ **COMPLETE** — move to Task 002

---

## ❌ Fail Scenarios

**If you see:**
- ❌ Video is still landscape (1920x1080) → crop filter failed
- ❌ Error in logs about "crop" → syntax error in filter
- ❌ Crash during render → OOM or ffmpeg issue
- ❌ Proxy preview wrong aspect ratio → proxy renderer broken

**Then:** Check `TESTING-001-VERTICAL-EXPORT.md` for debugging steps

---

## 🐛 Quick Debug

**Backend logs:**
```bash
tail -f /tmp/videopeen-pipeline.log  # if using tee
# Or watch terminal where uvicorn is running
```

**Check ffmpeg command:**
```bash
# Look for crop filter in logs:
grep -i "crop=" backend_output.log
# Should see: crop=w='min(iw,ih*9/16)':h=...
```

**Test ffmpeg manually:**
```bash
# Test vertical crop
ffmpeg -i ~/Downloads/IMG_2748.MOV -vf "crop=w='min(iw,ih*9/16)':h='min(ih,iw*16/9)':x='(iw-min(iw,ih*9/16))/2':y='(ih-min(ih,iw*16/9))/2',scale=1080:1920" -t 5 /tmp/test_vertical.mp4

# Check output
ffprobe /tmp/test_vertical.mp4 2>&1 | grep Stream
# Should show 1080x1920
```

---

## 📱 Visual Test

**Upload to phone:**
```bash
# AirDrop or upload to cloud
# Play on phone
# Should fill screen vertically (no black bars)
```

---

## 🎯 Full Test Suite

For comprehensive testing, see: **`TESTING-001-VERTICAL-EXPORT.md`**

---

## 📋 Quick Checklist

- [ ] Backend starts without errors
- [ ] Frontend loads correctly
- [ ] Modal shows aspect ratio selector (📱 ⬜ 🖥)
- [ ] 9:16 creates vertical project
- [ ] Proxy preview is vertical
- [ ] Final render is 1080×1920
- [ ] Export downloads correctly
- [ ] Video plays on phone

**All checked?** → 🎉 Task complete!
