from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ThreatType = Literal["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE"]


class LinkSafetyRequest(BaseModel):
    url: str = Field(min_length=1, max_length=4096)


class LinkSafetyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result_id: str
    input_type: Literal["link_safety"] = "link_safety"
    processing_status: Literal["completed"] = "completed"
    submitted_url: str
    checked_url: str
    provider: Literal["Google Web Risk"] = "Google Web Risk"
    safety_status: Literal["threat_detected", "no_known_threats"]
    threat_types: list[ThreatType] = Field(default_factory=list)
    checked_at: datetime
    threat_expires_at: datetime | None = None
    cached: bool = False
    explanation: str
    recommended_action: str
    limitations: str = (
        "This checks Google's known threat lists, not whether the webpage's claims are true. "
        "New threats and redirect destinations may not be detected. "
        "No known threats found does not guarantee safety; warnings can also be mistaken."
    )
    pipeline_version: Literal["link-safety-v1"] = "link-safety-v1"
    created_at: datetime

    @model_validator(mode="after")
    def consistent_verdict(self):
        if (self.safety_status == "threat_detected") != bool(self.threat_types):
            raise ValueError("The safety status must match the returned threat types")
        return self


class FailedLinkSafetyRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result_id: str
    input_type: Literal["link_safety"] = "link_safety"
    processing_status: Literal["failed"] = "failed"
    submitted_url: str
    checked_url: str
    provider: Literal["Google Web Risk"] = "Google Web Risk"
    error_code: str
    message: str
    retryable: bool = True
    pipeline_version: Literal["link-safety-v1"] = "link-safety-v1"
    created_at: datetime
