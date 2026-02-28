# Task 004: Upload Progress Bar

**Priority:** 🟡 HIGH
**Effort:** 1 day
**Status:** ⬜ NOT STARTED
**Depends on:** Nothing
**Assigned to:** —

---

## Goal

Show upload progress percentage when user uploads video files. Currently no feedback — user stares at nothing wondering if it's frozen.

## Why This Matters

- "Did it freeze?" anxiety kills user trust
- Large cooking videos (500MB-2GB) take 30-60+ seconds to upload
- Simple fix, big UX improvement

## What To Change

### Frontend Only (Backend already streams chunks)

#### 1. `frontend/lib/api.ts` — Add upload progress callback

Current `uploadVideo()` uses fetch. Switch to XMLHttpRequest for progress events:

```typescript
uploadVideo: (projectId: string, file: File, onProgress?: (pct: number) => void): Promise<UploadedVideo> => {
    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        const formData = new FormData();
        formData.append('file', file);
        
        xhr.upload.onprogress = (e) => {
            if (e.lengthComputable && onProgress) {
                onProgress(Math.round((e.loaded / e.total) * 100));
            }
        };
        
        xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) {
                resolve(JSON.parse(xhr.responseText));
            } else {
                reject(new Error(`Upload failed: ${xhr.status}`));
            }
        };
        
        xhr.onerror = () => reject(new Error('Upload failed'));
        
        xhr.open('POST', `${API_BASE}/api/projects/${projectId}/upload`);
        xhr.setRequestHeader('x-user-email', getUserEmail());
        xhr.send(formData);
    });
}
```

#### 2. `frontend/app/dashboard/new/page.tsx` or upload component — Show progress bar

```tsx
// Per-file progress tracking
const [uploadProgress, setUploadProgress] = useState<Record<string, number>>({});

// During upload:
for (const file of files) {
    await api.uploadVideo(projectId, file, (pct) => {
        setUploadProgress(prev => ({ ...prev, [file.name]: pct }));
    });
}

// UI: Simple progress bar per file
{Object.entries(uploadProgress).map(([name, pct]) => (
    <div key={name}>
        <span>{name}: {pct}%</span>
        <div className="bg-gray-700 rounded-full h-2">
            <div className="bg-orange-500 h-2 rounded-full" style={{ width: `${pct}%` }} />
        </div>
    </div>
))}
```

---

## Checklist

- [x] Frontend: Switch upload to XMLHttpRequest with progress events ✅ (was already done)
- [x] Frontend: Progress bar UI per file (name + percentage + bar) ✅ 
- [x] Frontend: "Uploading 2/3 files..." overall status ✅
- [x] Frontend: Error state if upload fails (retry instructions) ✅
- [ ] Test: Upload 500MB video → smooth progress 0-100%
- [ ] Test: Upload multiple files → individual progress bars

## Implementation Summary

**Completed:** 2026-02-28
**Status:** ✅ CODE COMPLETE - Ready for testing

### Changes Made

#### Frontend: `app/dashboard/page.tsx`

**Enhanced upload progress UI:**

1. **Overall Upload Status** - Shows "Uploading X/Y files..." with overall percentage at the top of the file list during upload

2. **Enhanced Progress Bars:**
   - Smooth gradient animation (orange to lighter orange)
   - Percentage display next to each progress bar
   - Rounded corners for modern look
   - Smooth transitions (300ms ease-out)

3. **Improved File List UI:**
   - Better spacing and hover effects
   - File size display
   - Status indicators:
     - 🎥 Video icon for each file
     - ✓ Green checkmark when uploaded
     - ✕ Red error badge if failed
   - Truncated file names to prevent overflow

4. **Error Handling:**
   - Prominent error display with red background
   - Clear retry instructions: "Click 'Generate Video' to retry"
   - Individual file error states with visual feedback

5. **Visual Polish:**
   - Dark theme (#0a0a0a background, #111 modals)
   - Orange accent (#f97316) for progress bars
   - Smooth hover states and transitions
   - Clean typography and spacing

### Technical Notes

- Upload progress callback already implemented with XMLHttpRequest (no changes needed to api.ts)
- Progress is tracked per-file in component state
- Overall progress calculated as: uploaded files / total files
- Retry logic: Users click "Generate Video" again to retry failed uploads
- All existing functionality preserved (aspect ratio selector, etc.)

### Testing Needed

- [ ] Upload single large file (500MB+) → verify smooth 0-100% progress
- [ ] Upload multiple files → verify individual progress bars update independently
- [ ] Simulate network error → verify error state displays correctly
- [ ] Verify retry by clicking "Generate Video" again works after error

## Technical Notes

- Backend already handles chunked upload (1MB chunks via aiofiles) — no backend changes needed
- XMLHttpRequest is old-school but only reliable way to get upload progress
- fetch() API has no upload progress support (ReadableStream workaround is complex)
- Alternative: use axios which has built-in progress support
