from pydantic import BaseModel, Field

from app.pipeline.shared.models import (
    EvidenceItem,
    TextAnalysisResult,
)


class TextAnalysisRequest(BaseModel):
    text: str = Field(
        min_length=1,
        max_length=5000
    )


class PipelineErrorDetail(BaseModel):
    error_code: str
    message: str
    stage: str
    retryable: bool


class PipelineErrorResponse(BaseModel):
    detail: PipelineErrorDetail


__all__ = [
    "EvidenceItem",
    "PipelineErrorDetail",
    "PipelineErrorResponse",
    "TextAnalysisRequest",
    "TextAnalysisResult",
]
