"""FastAPI application entry point."""

from __future__ import annotations

import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings
from app.routers import projects, upload, process, user_settings, edit_plan
from app.websocket import ws_manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="VideoPeen", version="0.1.0", description="AI-powered cooking video editor")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(projects.router)
app.include_router(upload.router)
app.include_router(process.router)
app.include_router(user_settings.router)
app.include_router(edit_plan.router)

# Static files for uploads and outputs
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")
app.mount("/outputs", StaticFiles(directory=settings.output_dir), name="outputs")


@app.on_event("startup")
async def startup() -> None:
    logger.info("Connecting to MongoDB at %s", settings.mongodb_uri)
    client = AsyncIOMotorClient(settings.mongodb_uri)
    app.state.db = client[settings.mongodb_db]
    logger.info("Connected to database: %s", settings.mongodb_db)


@app.on_event("shutdown")
async def shutdown() -> None:
    if hasattr(app.state, "db"):
        app.state.db.client.close()
        logger.info("MongoDB connection closed")


@app.websocket("/ws/{project_id}")
async def websocket_endpoint(websocket: WebSocket, project_id: str) -> None:
    await ws_manager.connect(project_id, websocket)
    try:
        while True:
            # Keep connection alive; client can send pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(project_id, websocket)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
