from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProjectStatus(str, Enum):
    CREATED = "created"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    ANALYZING = "analyzing"
    SELECTING = "selecting"
    REVIEW = "review"
    STITCHING = "stitching"
    COMPLETED = "completed"
    ERROR = "error"


# ---------------------------------------------------------------------------
# MongoDB document schemas (used with motor – no ORM, just Pydantic for
# serialisation / validation).
# ---------------------------------------------------------------------------


class Segment(BaseModel):
    index: int
    start_time: float
    end_time: float
    path: str  # path to the segment file on disk


class VideoClip(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    project_id: str
    filename: str
    original_path: str
    duration: float = 0.0
    segments: list[Segment] = []

    class Config:
        populate_by_name = True


class VideoAnalysis(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    project_id: str
    clip_id: str
    segment_index: int
    chunk_index: int
    start_time: float
    end_time: float
    description: str = ""
    tags: list[str] = []

    class Config:
        populate_by_name = True


class EditDecision(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    project_id: str
    sequence_order: int
    source_clip_id: str
    start_time: float
    end_time: float
    reason: str = ""

    class Config:
        populate_by_name = True


class Project(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    name: str
    recipe_details: str = ""
    dish_name: str = ""
    instructions: str = ""
    output_duration: int = 60  # seconds
    chunk_size: int = 120  # seconds
    aspect_ratio: str = "16:9"  # "16:9", "9:16", "1:1"
    status: ProjectStatus = ProjectStatus.CREATED
    progress: float = 0.0
    current_step: str = ""
    output_path: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    class Config:
        populate_by_name = True


# ---------------------------------------------------------------------------
# Request / response helpers
# ---------------------------------------------------------------------------


class ProjectCreate(BaseModel):
    name: Optional[str] = None
    recipe_details: str = ""
    dish_name: str = ""
    instructions: str = ""
    output_duration: int = 60
    chunk_size: int = 120
    aspect_ratio: str = "16:9"  # Default to 16:9 for backward compatibility


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    recipe_details: Optional[str] = None
    dish_name: Optional[str] = None
    instructions: Optional[str] = None
    output_duration: Optional[int] = None
    chunk_size: Optional[int] = None
    aspect_ratio: Optional[str] = None


class ProcessRequest(BaseModel):
    output_duration: Optional[int] = None
    chunk_size: Optional[int] = None
