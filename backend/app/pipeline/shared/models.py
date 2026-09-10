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
AssessmentOutcome = Literal[
    "supported", "contradicted", "unsupported", "conflicting",
    "insufficient_evidence", "not_checkable",
]
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


class DateContext(PipelineModel):
    """A visible interpretation of a yearless date, never a source quotation."""

    claim_text: str = Field(min_length=1, max_length=100)
    month: int = Field(ge=1, le=12)
    day: int | None = Field(default=None, ge=1, le=31)
    year: int = Field(ge=1900, le=2199)
    basis: Literal["assumed_current_year"] = "assumed_current_year"
    as_of: date
    display_date: str = Field(min_length=1, max_length=50)
    is_future: bool


class ClaimAnalysis(PipelineModel):
    """Matthew -> Chu and Donovan handoff."""

    extracted_claim: str | None = None
    claim_category: ClaimCategory
    checkable: bool
    classification_reason: str = Field(min_length=1)
    claim_confidence: Confidence
    date_context: DateContext | None = None

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


class EvidenceProvenance(PipelineModel):
    """Observable retrieval decisions, not a certification of source truth."""

    source_policy: Literal["catalogue", "government_namespace"]
    source_reason: str = Field(min_length=1, max_length=500)
    origin_group: str = Field(min_length=1, max_length=255)
    discovery_method: Literal["google_fact_check", "preferred_search", "web_search", "source_link"]
    relevance: Literal["direct", "context"]
    relevance_reason: str = Field(min_length=1, max_length=800)
    relevance_quote: str = Field(min_length=1, max_length=1800)
    applicability: Literal["established", "missing_context", "different_scope", "uncertain_time"]
    applicability_reason: str = Field(min_length=1, max_length=800)
    condition_quotes: list[str] = Field(default_factory=list, max_length=4)


class RetrievalTrace(PipelineModel):
    """Bounded diagnostics for evaluation; no credentials or raw provider errors."""

    search_requests: int = 0
    extraction_urls: int = 0
    relevance_calls: int = 0
    decisions: list[dict[str, str]] = Field(default_factory=list)


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
    provenance: EvidenceProvenance | None = None


class RetrievalResult(PipelineModel):
    """Chu -> Poon and Donovan handoff."""

    retrieval_status: RetrievalStatus
    evidence: list[EvidenceCandidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    trace: RetrievalTrace | None = None

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
    evidence_quote: str | None = None


class ClaimComparison(PipelineModel):
    """A grounded comparison, not a standalone truth verdict."""

    aspect: Literal["amount", "frequency", "population", "start_date", "requirement", "other"]
    claim_text: str = Field(min_length=1, max_length=5000)
    finding: Literal["matches", "differs", "unresolved"]
    applies_to_claim: bool
    explanation: str = Field(min_length=1, max_length=1200)
    evidence_id: str | None = None
    evidence_quote: str | None = Field(default=None, max_length=1800)

    @model_validator(mode="after")
    def validate_grounding(self):
        if self.finding != "unresolved" and (not self.evidence_id or not self.evidence_quote):
            raise ValueError("A comparison finding requires cited evidence")
        if self.evidence_quote and not self.evidence_id:
            raise ValueError("A comparison quote requires an evidence ID")
        if self.finding == "unresolved" and self.applies_to_claim:
            raise ValueError("An unresolved comparison cannot establish applicability")
        return self


class AssessmentResult(PipelineModel):
    """Poon -> Donovan handoff."""

    concern_label: ConcernLabel
    misinformation_risk_score: RiskScore | None = None
    uncertainty: UncertaintyLevel
    uncertainty_reasons: list[str] = Field(min_length=1)
    explanation: str = Field(min_length=1)
    recommended_action: str = Field(min_length=1)
    assessed_evidence: list[AssessedEvidence] = Field(default_factory=list)
    assessment_outcome: AssessmentOutcome | None = None
    claim_comparisons: list[ClaimComparison] = Field(default_factory=list, max_length=37)

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
    assessment_reason: str | None = None
    evidence_quote: str | None = None
    provenance: EvidenceProvenance | None = None


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
    assessment_outcome: AssessmentOutcome | None = None
    claim_comparisons: list[ClaimComparison] = Field(default_factory=list, max_length=37)
    date_context: DateContext | None = None
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
        sources = {item.evidence_id: item for item in self.evidence}
        if self.date_context and self.date_context.claim_text not in (self.extracted_claim or ""):
            raise ValueError("Assumed date must refer to the identified claim")
        for item in self.claim_comparisons:
            if item.claim_text not in (self.extracted_claim or ""):
                raise ValueError("Comparison text must come from the identified claim")
            if item.evidence_id:
                if item.evidence_id not in sources:
                    raise ValueError("Comparison must cite a returned source")
                if item.evidence_quote and item.evidence_quote not in sources[item.evidence_id].passage:
                    raise ValueError("Comparison quote must come from its cited passage")
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
