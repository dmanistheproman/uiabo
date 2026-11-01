from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


ConcernLabel = Literal[
    "Low Concern",
    "Needs Caution",
    "High Concern",
    "Not Enough Information",
]


class ImageContextModel(BaseModel):
    """Base model for Check Image Context records."""

    model_config = ConfigDict(extra="forbid")


class ImageContextEvidenceLink(ImageContextModel):
    title: str
    url: str
    relationship: Literal[
        "supports",
        "contradicts",
        "context",
    ]
    summary: str


class ImageContextAnalysisResult(ImageContextModel):
    result_id: str

    input_type: Literal["image_context"] = "image_context"
    processing_status: Literal["completed"] = "completed"

    concern_label: ConcernLabel
    explanation: str
    evidence_links: list[ImageContextEvidenceLink]

    image_filename: str | None = None
    extracted_caption: str

    pipeline_version: str
    created_at: datetime


class FailedImageContextAnalysisRecord(ImageContextModel):
    result_id: str

    input_type: Literal["image_context"] = "image_context"
    processing_status: Literal["failed"] = "failed"

    error_code: str
    message: str
    retryable: bool

    pipeline_version: str
    created_at: datetime