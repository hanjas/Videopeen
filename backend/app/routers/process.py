"""Processing trigger and output download endpoints."""

from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.models.project import ProcessRequest, ProjectStatus
from app.services.pipeline import run_pipeline

router = APIRouter(prefix="/api/projects/{project_id}", tags=["process"])


@router.post("/process")
async def start_processing(project_id: str, body: ProcessRequest, request: Request):
    db = request.app.state.db
    project = await db.projects.find_one({"_id": project_id})
    if not project:
        raise HTTPException(404, "Project not found")

    if project.get("status") in (ProjectStatus.PROCESSING.value, ProjectStatus.ANALYZING.value,
                                  ProjectStatus.SELECTING.value, ProjectStatus.STITCHING.value):
        raise HTTPException(409, "Project is already being processed")

    # Apply overrides if provided
    updates = {}
    if body.output_duration is not None:
        updates["output_duration"] = body.output_duration
    if body.chunk_size is not None:
        updates["chunk_size"] = body.chunk_size
    if updates:
        await db.projects.update_one({"_id": project_id}, {"$set": updates})

    # Clear previous analysis/decisions/edit plans
    await db.video_analyses.delete_many({"project_id": project_id})
    await db.edit_decisions.delete_many({"project_id": project_id})
    await db.edit_plans.delete_many({"project_id": project_id})

    # Launch pipeline in background
    asyncio.create_task(run_pipeline(db, project_id))

    return {"message": "Processing started", "project_id": project_id}


@router.get("/output")
async def download_output(project_id: str, request: Request):
    db = request.app.state.db
    project = await db.projects.find_one({"_id": project_id})
    if not project:
        raise HTTPException(404, "Project not found")

    output_path = project.get("output_path")
    if not output_path or not os.path.exists(output_path):
        raise HTTPException(404, "Output not ready yet")

    return FileResponse(
        output_path,
        media_type="video/mp4",
        filename=f"{project.get('name', 'output')}.mp4",
    )
