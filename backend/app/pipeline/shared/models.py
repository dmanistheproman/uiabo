"""Shared Sprint 1 interfaces used between pipeline components.

These models are the contract between team members. Component implementations
may change internally, but their public inputs and outputs must validate against
these models before they enter the orchestrator.
"""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


ClaimCategory = Literal[
    "factual",
    "opinion",
    "joke_or_satire",
    "prediction",
    "personal_experience",
    "unverifiable",
]
ConcernLabel = Literal[
    "Low Concern",
    "Needs Caution",
    "High Concern",
    "Not Enough Information",
]
EvidenceStance = Literal["supporting", "contradicting", "neutral"]
RetrievalStatus = Literal["completed", "no_evidence", "failed"]
SourceType = Literal[
    "fact_check",
    "government",
    "academic",
    "news",
    "other",
]
UncertaintyLevel = Literal["Low", "Medium", "High"]

Confidence = Annotated[float, Field(ge=0.0, le=1.0)]
RiskScore = Annotated[int, Field(ge=0, le=100)]


class PipelineModel(BaseModel):
    """Strict base class that rejects accidental interface changes."""

    model_config = ConfigDict(extra="forbid")


class PreparedText(PipelineModel):
    """Yi Da -> Matthew handoff."""

    original_text: str
    normalised_text: str = Field(min_length=1, max_length=5000)
    language: str = Field(min_length=2, max_length=16)
    warnings: list[str] = Field(default_factory=list)


class ClaimAnalysis(PipelineModel):
    """Matthew -> Chu and Donovan handoff."""

    extracted_claim: str | None = None
    claim_category: ClaimCategory
    checkable: bool
    classification_reason: str = Field(min_length=1)
    claim_confidence: Confidence

    @model_validator(mode="after")
    def validate_checkability(self) -> "ClaimAnalysis":
        if self.checkable and not self.extracted_claim:
            raise ValueError(
                "A checkable claim must include extracted_claim."
            )
        if self.checkable and self.claim_category != "factual":
            raise ValueError(
                "Only factual claims can be marked checkable in Sprint 1."
            )
        return self


class EvidenceCandidate(PipelineModel):
    """One source returned by Chu's retrieval component."""

    evidence_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: AnyHttpUrl
    publisher: str = Field(min_length=1)
    author: str | None = None
    published_at: date | None = None
    passage: str = Field(min_length=1)
    source_type: SourceType
    retrieval_score: Confidence
    retrieved_at: datetime


class RetrievalResult(PipelineModel):
    """Chu -> Poon and Donovan handoff."""

    retrieval_status: RetrievalStatus
    evidence: list[EvidenceCandidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_status_and_evidence(self) -> "RetrievalResult":
        if self.retrieval_status == "completed" and not self.evidence:
            raise ValueError(
                "Completed retrieval must include at least one evidence item."
            )
        if self.retrieval_status != "completed" and self.evidence:
            raise ValueError(
                "no_evidence and failed retrievals cannot contain evidence."
            )
        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("Evidence IDs must be unique.")
        return self


class AssessedEvidence(PipelineModel):
    """Poon's assessment of one retrieved evidence item."""

    evidence_id: str = Field(min_length=1)
    stance: EvidenceStance
    quality_score: Confidence
    assessment_reason: str = Field(min_length=1)


class AssessmentResult(PipelineModel):
    """Poon -> Donovan handoff."""

    concern_label: ConcernLabel
    misinformation_risk_score: RiskScore | None = None
    uncertainty: UncertaintyLevel
    uncertainty_reasons: list[str] = Field(min_length=1)
    explanation: str = Field(min_length=1)
    recommended_action: str = Field(min_length=1)
    assessed_evidence: list[AssessedEvidence] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_score_and_label(self) -> "AssessmentResult":
        no_information = self.concern_label == "Not Enough Information"
        if no_information and self.misinformation_risk_score is not None:
            raise ValueError(
                "Not Enough Information must have a null risk score."
            )
        if not no_information and self.misinformation_risk_score is None:
            raise ValueError(
                "A concern assessment must include a risk score."
            )
        evidence_ids = [item.evidence_id for item in self.assessed_evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("Assessed evidence IDs must be unique.")
        return self


class EvidenceItem(PipelineModel):
    """Evidence returned to the application in the final API response."""

    evidence_id: str
    title: str
    url: AnyHttpUrl
    publisher: str
    published_at: date | None = None
    passage: str
    source_type: SourceType
    stance: EvidenceStance
    quality_score: Confidence


class TextAnalysisResult(PipelineModel):
    """Successful final API response assembled by Donovan."""

    result_id: str = Field(min_length=1)
    processing_status: Literal["completed"] = "completed"
    original_text: str
    extracted_claim: str | None = None
    claim_category: ClaimCategory
    checkable: bool
    concern_label: ConcernLabel
    misinformation_risk_score: RiskScore | None = None
    uncertainty: UncertaintyLevel
    uncertainty_reasons: list[str] = Field(min_length=1)
    explanation: str = Field(min_length=1)
    recommended_action: str = Field(min_length=1)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    pipeline_version: str = Field(min_length=1)
    created_at: datetime

    @model_validator(mode="after")
    def validate_final_result(self) -> "TextAnalysisResult":
        no_information = self.concern_label == "Not Enough Information"
        if no_information and self.misinformation_risk_score is not None:
            raise ValueError(
                "Not Enough Information must have a null risk score."
            )
        if not no_information and self.misinformation_risk_score is None:
            raise ValueError(
                "A concern assessment must include a risk score."
            )
        if self.checkable and not self.extracted_claim:
            raise ValueError(
                "A checkable result must include extracted_claim."
            )
        return self


class FailedAnalysisRecord(PipelineModel):
    """Internal Firestore record for a pipeline run that failed."""

    result_id: str
    processing_status: Literal["failed"] = "failed"
    original_text: str
    failure_stage: str
    error_code: str
    message: str
    retryable: bool
    warnings: list[str] = Field(default_factory=list)
    pipeline_version: str
    created_at: datetime

