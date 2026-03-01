"""Project CRUD endpoints."""

from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.models.project import ProjectCreate, ProjectStatus, ProjectUpdate

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _generate_project_name(dish_name: str = "") -> str:
    """Generate a project name in format '{dish_name} - {Mon DD}' or 'Cooking Video - {Mon DD}'."""
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%b %d")  # e.g., "Feb 22"
    
    if dish_name and dish_name.strip():
        return f"{dish_name.strip()} - {date_str}"
    return f"Cooking Video - {date_str}"


def _db(request: Request):
    return request.app.state.db


def _get_user(request: Request) -> str | None:
    """Extract user email from X-User-Email header. Returns None if missing/anonymous."""
    email = request.headers.get("x-user-email", "")
    if not email or email == "anonymous":
        return None
    return email


@router.post("", status_code=201)
async def create_project(body: ProjectCreate, request: Request) -> dict[str, Any]:
    db = _db(request)
    user = _get_user(request)
    doc = body.model_dump()
    
    # Auto-generate name if not provided
    if not doc.get("name") or not doc["name"].strip():
        doc["name"] = _generate_project_name(doc.get("dish_name", ""))
    
    doc["_id"] = str(uuid.uuid4())
    doc["user_email"] = user
    doc["status"] = ProjectStatus.CREATED.value
    doc["progress"] = 0.0
    doc["current_step"] = ""
    doc["output_path"] = None
    doc["created_at"] = datetime.now(timezone.utc)
    doc["updated_at"] = datetime.now(timezone.utc)
    await db.projects.insert_one(doc)
    return doc


@router.get("")
async def list_projects(request: Request) -> list[dict[str, Any]]:
    db = _db(request)
    user = _get_user(request)
    query = {"user_email": user} if user else {}
    cursor = db.projects.find(query).sort("created_at", -1)
    return await cursor.to_list(100)


@router.get("/{project_id}")
async def get_project(project_id: str, request: Request) -> dict[str, Any]:
    db = _db(request)
    user = _get_user(request)
    query: dict[str, Any] = {"_id": project_id}
    if user:
        query["user_email"] = user
    project = await db.projects.find_one(query)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@router.patch("/{project_id}")
async def update_project(project_id: str, body: ProjectUpdate, request: Request) -> dict[str, Any]:
    db = _db(request)
    user = _get_user(request)
    query: dict[str, Any] = {"_id": project_id}
    if user:
        query["user_email"] = user
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No fields to update")
    updates["updated_at"] = datetime.now(timezone.utc)
    result = await db.projects.update_one(query, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(404, "Project not found")
    return await db.projects.find_one({"_id": project_id})


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str, request: Request) -> None:
    db = _db(request)
    user = _get_user(request)
    query: dict[str, Any] = {"_id": project_id}
    if user:
        query["user_email"] = user
    result = await db.projects.delete_one(query)
    if result.deleted_count == 0:
        raise HTTPException(404, "Project not found")
    # Clean up related collections
    await db.video_clips.delete_many({"project_id": project_id})
    await db.video_analyses.delete_many({"project_id": project_id})
    await db.edit_plans.delete_many({"project_id": project_id})
    await db.edit_decisions.delete_many({"project_id": project_id})

    # Clean up files on disk
    upload_dir = Path(settings.upload_dir) / project_id
    if upload_dir.exists():
        shutil.rmtree(upload_dir, ignore_errors=True)
    output_dir = Path(settings.output_dir)
    if output_dir.exists():
        for f in output_dir.glob(f"{project_id}*"):
            f.unlink(missing_ok=True)


@router.get("/{project_id}/clips")
async def list_clips(project_id: str, request: Request) -> list[dict[str, Any]]:
    db = _db(request)
    return await db.video_clips.find({"project_id": project_id}).to_list(None)


@router.get("/{project_id}/analyses")
async def list_analyses(project_id: str, request: Request) -> list[dict[str, Any]]:
    db = _db(request)
    return await db.video_analyses.find({"project_id": project_id}).to_list(None)


@router.get("/{project_id}/decisions")
async def list_decisions(project_id: str, request: Request) -> list[dict[str, Any]]:
    db = _db(request)
    return await db.edit_decisions.find({"project_id": project_id}, {"_id": 0}).sort("sequence_order", 1).to_list(None)
