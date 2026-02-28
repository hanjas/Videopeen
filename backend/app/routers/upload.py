"""Video upload endpoint."""

from __future__ import annotations

import os
import uuid

import aiofiles
from fastapi import APIRouter, HTTPException, Request, UploadFile, File

from app.config import settings

router = APIRouter(prefix="/api/projects/{project_id}/upload", tags=["upload"])


@router.post("")
async def upload_video(project_id: str, file: UploadFile = File(...), request: Request = None):
    db = request.app.state.db

    # Verify project exists
    project = await db.projects.find_one({"_id": project_id})
    if not project:
        raise HTTPException(404, "Project not found")

    # Validate file type — accept video/* or common video extensions
    video_extensions = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".wmv", ".flv"}
    ext_check = os.path.splitext(file.filename or "")[1].lower()
    is_video_mime = file.content_type and file.content_type.startswith("video/")
    is_video_ext = ext_check in video_extensions
    if not (is_video_mime or is_video_ext):
        raise HTTPException(400, "Only video files are accepted")

    # Save file to disk
    clip_id = str(uuid.uuid4())
    project_upload_dir = os.path.join(settings.upload_dir, project_id)
    os.makedirs(project_upload_dir, exist_ok=True)

    # Preserve original extension
    ext = os.path.splitext(file.filename or "video.mp4")[1] or ".mp4"
    filename = f"{clip_id}{ext}"
    file_path = os.path.join(project_upload_dir, filename)

    async with aiofiles.open(file_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):  # 1 MB chunks
            await f.write(chunk)

    # Create clip record in MongoDB
    clip_doc = {
        "_id": clip_id,
        "project_id": project_id,
        "filename": file.filename or filename,
        "original_path": file_path,
        "duration": 0.0,
        "segments": [],
    }
    await db.video_clips.insert_one(clip_doc)

    return {
        "clip_id": clip_id,
        "filename": clip_doc["filename"],
        "path": file_path,
    }


@router.get("")
async def list_uploads(project_id: str, request: Request):
    db = request.app.state.db
    clips = await db.video_clips.find({"project_id": project_id}).to_list(None)
    return clips
