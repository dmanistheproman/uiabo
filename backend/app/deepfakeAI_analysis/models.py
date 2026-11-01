from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

class DeepfakeAIModel(BaseModel):
    """Base model for deepfake analysis schemas."""

    model_config = ConfigDict(extra="forbid")

class DeepfakeAI_Explanation(DeepfakeAIModel):
    visual_evidence: list[str] | None = None
    reasoning: str
    limitations: str | None = None


class DeepfakeAI_AnalysisResult(DeepfakeAIModel):
    result_id: str
    filename: str | None = None

    input_type: Literal["deepfake_ai"] = "deepfake_ai"
    processing_status: Literal["completed"] = "completed"

    label: Literal["Real", "Fake", "Uncertain"]
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    real_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    fake_probability: float | None = Field(default=None, ge=0.0, le=1.0)

    explanation: DeepfakeAI_Explanation | None = None

    pipeline_version: str
    created_at: datetime


class FailedDeepfakeAI_AnalysisRecord(DeepfakeAIModel):
    result_id: str
    input_type: Literal["deepfake_ai"] = "deepfake_ai"
    processing_status: Literal["failed"] = "failed"

    error_code: str
    message: str
    retryable: bool

    pipeline_version: str
    created_at: datetime