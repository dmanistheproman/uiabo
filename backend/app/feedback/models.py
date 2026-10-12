"""Models for user feedback and System Administrator review."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


FeedbackCategory = Literal[
    "general_feedback",
    "service_review",
]

FeedbackStatus = Literal[
    "submitted",
    "reviewed",
]


class FeedbackModel(BaseModel):
    """Base model shared by feedback records."""

    model_config = ConfigDict(extra="forbid")


class FeedbackRecord(FeedbackModel):
    """One feedback record stored by uiabo."""

    feedback_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)

    category: FeedbackCategory

    rating: int | None = Field(
        default=None,
        ge=1,
        le=5,
    )

    comments: str | None = Field(
        default=None,
        max_length=1000,
    )

    status: FeedbackStatus = "submitted"

    created_at: datetime

    reviewed_at: datetime | None = None
    reviewed_by: str | None = None


class FeedbackSubmissionRequest(FeedbackModel):
    """Request used by an app user to submit feedback."""

    category: FeedbackCategory

    rating: int | None = Field(
        default=None,
        ge=1,
        le=5,
    )

    comments: str | None = Field(
        default=None,
        max_length=1000,
    )


class FeedbackReviewRequest(FeedbackModel):
    """Request used by a System Administrator to review feedback."""

    status: Literal["reviewed"]
