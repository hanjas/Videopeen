#!/usr/bin/env python3
"""
Gemini Direct Video Analysis Test
- Compress video with ffmpeg (720p, 30fps, <=50MB)
- Upload to Gemini Files API
- Analyze cooking actions with timestamps
Uses only stdlib (no requests needed)
"""

import subprocess
import os
import sys
import time
import json
import urllib.request
import urllib.error

API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    sys.exit("GEMINI_API_KEY not set")

SOURCE = "/Users/roshinhanjas/Downloads/Media/Videos/Bread Toast/IMG_1906.MOV"
COMPRESSED = "/tmp/bread_toast_compressed.mp4"
MODEL = "gemini-2.5-flash"
BASE_URL = "https://generativelanguage.googleapis.com"


def api_request(url, data=None, headers=None, method=None):
    """Simple urllib wrapper"""
    headers = headers or {}
    if isinstance(data, dict):
        data = json.dumps(data).encode()
        headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return resp.status, json.loads(resp.read()), dict(resp.headers)
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return e.code, {"error": body[:500]}, {}


# --- Step 1: Compress with ffmpeg ---
print("=" * 60)
print("STEP 1: Compressing video with ffmpeg")
print("=" * 60)

cmd = [
    "ffmpeg", "-y",
    "-i", SOURCE,
    # "-t", "30",  # full video
    "-vf", "scale=-2:720",
    "-r", "30",
    "-c:v", "libx264",
    "-crf", "28",
    "-preset", "fast",
    "-c:a", "aac",
    "-b:a", "64k",
    COMPRESSED
]

start = time.time()
result = subprocess.run(cmd, capture_output=True, text=True)
if result.returncode != 0:
    print(f"ffmpeg error: {result.stderr[-500:]}")
    sys.exit(1)

compress_time = time.time() - start
size_mb = os.path.getsize(COMPRESSED) / (1024 * 1024)
print(f"  Compressed: {size_mb:.1f} MB in {compress_time:.1f}s")

if size_mb > 50:
    sys.exit(f"File too large: {size_mb:.1f} MB > 50 MB limit")

# --- Step 2: Upload to Gemini Files API ---
print()
print("=" * 60)
print("STEP 2: Uploading to Gemini Files API")
print("=" * 60)

start = time.time()

file_size = os.path.getsize(COMPRESSED)

# Start resumable upload
init_req = urllib.request.Request(
    f"{BASE_URL}/upload/v1beta/files?key={API_KEY}",
    data=json.dumps({"file": {"display_name": "bread_toast_test"}}).encode(),
    headers={
        "X-Goog-Upload-Protocol": "resumable",
        "X-Goog-Upload-Command": "start",
        "X-Goog-Upload-Header-Content-Length": str(file_size),
        "X-Goog-Upload-Header-Content-Type": "video/mp4",
        "Content-Type": "application/json",
    },
)

with urllib.request.urlopen(init_req) as resp:
    upload_url = resp.headers.get("X-Goog-Upload-URL")
    if not upload_url:
        sys.exit("No upload URL returned")

# Upload the actual file
with open(COMPRESSED, "rb") as f:
    file_data = f.read()

upload_req = urllib.request.Request(
    upload_url,
    data=file_data,
    headers={
        "X-Goog-Upload-Command": "upload, finalize",
        "X-Goog-Upload-Offset": "0",
        "Content-Length": str(len(file_data)),
    },
)

with urllib.request.urlopen(upload_req, timeout=120) as resp:
    upload_result = json.loads(resp.read())

file_uri = upload_result.get("file", {}).get("uri")
file_name = upload_result.get("file", {}).get("name")
file_state = upload_result.get("file", {}).get("state")

upload_time = time.time() - start
print(f"  Uploaded in {upload_time:.1f}s")
print(f"  File URI: {file_uri}")
print(f"  State: {file_state}")

# --- Step 3: Wait for processing ---
print()
print("=" * 60)
print("STEP 3: Waiting for file processing")
print("=" * 60)

start = time.time()
while True:
    status_code, resp_data, _ = api_request(
        f"{BASE_URL}/v1beta/{file_name}?key={API_KEY}"
    )
    state = resp_data.get("state", resp_data.get("error", "unknown"))
    if state == "ACTIVE":
        print(f"  File active! ({time.time() - start:.1f}s)")
        break
    elif state == "FAILED":
        sys.exit(f"  File processing failed: {resp_data}")
    else:
        print(f"  State: {state} (waiting...)")
        time.sleep(3)

# --- Step 4: Analyze with Gemini ---
print()
print("=" * 60)
print("STEP 4: Analyzing video with Gemini 2.5 Flash")
print("=" * 60)

prompt = """You are a cooking video analyzer. Watch this cooking video carefully and identify every distinct cooking action/step.

For each action, provide:
1. **Timestamp** (start - end in MM:SS format)
2. **Action** (what's happening)
3. **Details** (ingredients, tools, technique)

Also note:
- Any scene changes or camera movements
- Audio cues (sizzling, chopping sounds, speech)
- Ingredient additions
- Cooking state changes (raw → cooked, solid → melted, etc.)

Be precise with timestamps. List actions in chronological order.
Output as a structured list."""

start = time.time()
status_code, result, _ = api_request(
    f"{BASE_URL}/v1beta/models/{MODEL}:generateContent?key={API_KEY}",
    data={
        "contents": [{
            "parts": [
                {"file_data": {"mime_type": "video/mp4", "file_uri": file_uri}},
                {"text": prompt}
            ]
        }],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 4096,
        }
    },
)

analysis_time = time.time() - start

if "candidates" in result:
    text = result["candidates"][0]["content"]["parts"][0]["text"]
    print(f"  Analysis complete in {analysis_time:.1f}s")
    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(text)

    usage = result.get("usageMetadata", {})
    print()
    print("=" * 60)
    print("USAGE")
    print("=" * 60)
    print(f"  Prompt tokens: {usage.get('promptTokenCount', '?')}")
    print(f"  Output tokens: {usage.get('candidatesTokenCount', '?')}")
    print(f"  Total tokens: {usage.get('totalTokenCount', '?')}")
    print(f"  Thinking tokens: {usage.get('thoughtsTokenCount', '?')}")
else:
    print(f"  Error: {json.dumps(result, indent=2)[:1000]}")

# --- Timing Summary ---
print()
print("=" * 60)
print("TIMING SUMMARY")
print("=" * 60)
print(f"  Compress:  {compress_time:.1f}s")
print(f"  Upload:    {upload_time:.1f}s")
print(f"  Analysis:  {analysis_time:.1f}s")
print(f"  TOTAL:     {compress_time + upload_time + analysis_time:.1f}s")

# Cleanup uploaded file
api_request(f"{BASE_URL}/v1beta/{file_name}?key={API_KEY}", method="DELETE")
print(f"\n  Cleaned up uploaded file.")
