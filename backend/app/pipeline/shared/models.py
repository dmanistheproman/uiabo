"""Shared Sprint 1 interfaces used between pipeline components.

These models are the contract between team members. Component implementations
may change internally, but their public inputs and outputs must validate against
these models before they enter the orchestrator.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Literal

from .credibility import CredibilityRating, build_credibility
from .component_assessment import ComponentAssessment, validate_component_result

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
    "insufficient_evidence", "not_checkable", "highly_unlikely",
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
    """Visible explicit or inferred dates, never a source quotation."""

    claim_text: str = Field(min_length=1, max_length=100)
    month: int = Field(ge=1, le=12)
    day: int | None = Field(default=None, ge=1, le=31)
    year: int = Field(ge=1900, le=2199)
    basis: Literal["assumed_current_year", "relative_submission_date", "explicit_date"] = "assumed_current_year"
    as_of: date
    display_date: str = Field(min_length=1, max_length=50)
    is_future: bool
    start_date: date | None = None
    end_date: date | None = None
    timezone: Literal["Asia/Singapore"] = "Asia/Singapore"

    @model_validator(mode="after")
    def validate_interval(self):
        if (self.start_date is None) != (self.end_date is None):
            raise ValueError("A date interval requires both boundaries.")
        if self.start_date and self.end_date < self.start_date:
            raise ValueError("A date interval must end on or after its start.")
        return self


class ClaimQuantity(PipelineModel):
    text: str = Field(min_length=1, max_length=100)
    value: float = Field(allow_inf_nan=False)
    unit: str = Field(min_length=1, max_length=30)


class ClaimContext(PipelineModel):
    """Grounded interpretation, separate from the unchanged original claim."""

    claim_type: Literal["general", "weather_forecast", "policy_change"] = "general"
    modality: Literal["asserted", "possible"] = "asserted"
    input_intent: Literal["assertion", "question", "hypothetical"] = "assertion"
    relationship: Literal["general", "management", "ownership", "funding"] = "general"
    location: str | None = Field(default=None, max_length=150)
    measurement: Literal["air_temperature", "apparent_temperature", "surface_temperature", "unspecified"] = "unspecified"
    quantities: list[ClaimQuantity] = Field(default_factory=list, max_length=12)
    as_of: date
    assessed_at: datetime
    assumptions: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def validate_submission_clock(self):
        if self.assessed_at.tzinfo is None:
            raise ValueError("Claim assessment time requires a timezone.")
        if self.assessed_at.astimezone(timezone(timedelta(hours=8))).date() != self.as_of:
            raise ValueError("Claim context must use the Singapore submission date.")
        return self


def _validate_claim_context(text, context, dates):
    if context is None:
        return
    text = text or ""
    if context.location and context.location not in text:
        raise ValueError("The interpreted location must come from the claim.")
    if any(item.text not in text for item in context.quantities):
        raise ValueError("Interpreted quantities must come from the claim.")
    if dates and dates.as_of != context.as_of:
        raise ValueError("Date and claim context must use the same submission date.")


class ForecastPeriod(PipelineModel):
    date: date
    low: float = Field(allow_inf_nan=False)
    high: float = Field(allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_temperatures(self):
        if self.low > self.high:
            raise ValueError("Forecast minimum cannot exceed maximum.")
        return self


class ForecastData(PipelineModel):
    location: str = Field(min_length=1, max_length=150)
    measurement: Literal["air_temperature"] = "air_temperature"
    unit: Literal["C"] = "C"
    issued_at: datetime
    reader_url: AnyHttpUrl | None = None
    periods: list[ForecastPeriod] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def validate_forecast(self):
        if self.issued_at.tzinfo is None:
            raise ValueError("Forecast issue time requires a timezone.")
        if len({item.date for item in self.periods}) != len(self.periods):
            raise ValueError("Forecast dates must be unique.")
        return self


class ForecastContext(PipelineModel):
    """Comparison with an issued forecast, not a guarantee about future weather."""

    status: Literal["supported_by_forecast", "not_supported_by_forecast", "mixed", "unresolved"]
    risk_basis: Literal["forecast_comparison"] | None = None
    scoring_rule: Literal["forecast-gap-v1"] | None = None
    deviation_c: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    explanation: str = Field(min_length=1, max_length=2400)
    limitations: list[str] = Field(default_factory=list, max_length=8)
    evidence_ids: list[str] = Field(default_factory=list, max_length=6)
    start_date: date | None = None
    end_date: date | None = None
    issued_at: datetime | None = None
    forecast_low: float | None = Field(default=None, allow_inf_nan=False)
    forecast_high: float | None = Field(default=None, allow_inf_nan=False)
    unit: Literal["C"] = "C"

    @model_validator(mode="after")
    def validate_risk_basis(self):
        if self.risk_basis is not None:
            if (self.status != "not_supported_by_forecast" or self.scoring_rule != "forecast-gap-v1"
                    or self.deviation_c is None or self.deviation_c < 2
                    or not self.evidence_ids or self.forecast_low is None or self.forecast_high is None
                    or self.issued_at is None or self.start_date is None or self.end_date is None):
                raise ValueError("Forecast-based risk requires a complete matching forecast comparison.")
        elif self.scoring_rule is not None or self.deviation_c is not None:
            raise ValueError("Forecast scoring details require an explicit forecast risk basis.")
        return self


class ClaimAnalysis(PipelineModel):
    """Matthew -> Chu and Donovan handoff."""

    extracted_claim: str | None = None
    claim_category: ClaimCategory
    checkable: bool
    classification_reason: str = Field(min_length=1)
    claim_confidence: Confidence
    date_context: DateContext | None = None
    claim_context: ClaimContext | None = None

    @model_validator(mode="after")
    def validate_checkability(self) -> "ClaimAnalysis":
        _validate_claim_context(self.extracted_claim, self.claim_context, self.date_context)
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

    source_policy: Literal["catalogue", "government_namespace", "scoped_first_party"]
    source_reason: str = Field(min_length=1, max_length=500)
    origin_group: str = Field(min_length=1, max_length=255)
    discovery_method: Literal["google_fact_check", "preferred_search", "web_search", "source_link", "official_api"]
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


class ClimateRecord(PipelineModel):
    location: Literal["Singapore"] = "Singapore"
    measurement: Literal["air_temperature"] = "air_temperature"
    scope: Literal["annual_all_stations"] = "annual_all_stations"
    maximum_c: float = Field(ge=30, le=60, allow_inf_nan=False)
    updated_at: date


class PlausibilityContext(PipelineModel):
    scoring_rule: Literal["sg-temperature-outlier-v1"] = "sg-temperature-outlier-v1"
    evidence_id: str = Field(min_length=1)
    claimed_c: float = Field(allow_inf_nan=False)
    record: ClimateRecord
    deviation_c: float = Field(ge=10, allow_inf_nan=False)
    explanation: str = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_gap(self):
        if abs(self.claimed_c - self.record.maximum_c - self.deviation_c) > .001:
            raise ValueError("Plausibility gap must match the cited historical record")
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
    provenance: EvidenceProvenance | None = None
    forecast: ForecastData | None = None
    climate_record: ClimateRecord | None = None
    # Whole-pool reading (pipeline-v3): the fetched page text the passage was
    # selected from. Optional; never persisted into results.
    full_text: str | None = None


class RetrievalResult(PipelineModel):
    """Chu -> Poon and Donovan handoff."""

    retrieval_status: RetrievalStatus
    failure_reason: Literal["source_pages_unavailable"] | None = None
    evidence: list[EvidenceCandidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    trace: RetrievalTrace | None = None

    @model_validator(mode="after")
    def validate_status_and_evidence(self) -> "RetrievalResult":
        if self.failure_reason is not None and self.retrieval_status != "failed":
            raise ValueError("Only failed retrievals can have a failure reason.")
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
    scope_limitation: str | None = Field(default=None, max_length=1200)

    @model_validator(mode="after")
    def validate_grounding(self):
        if self.finding != "unresolved" and (not self.evidence_id or not self.evidence_quote):
            raise ValueError("A comparison finding requires cited evidence")
        if self.evidence_quote and not self.evidence_id:
            raise ValueError("A comparison quote requires an evidence ID")
        if self.finding == "unresolved" and self.applies_to_claim:
            raise ValueError("An unresolved comparison cannot establish applicability")
        return self


class PolicyContext(PipelineModel):
    """Separate published-policy findings from verification of an alleged change."""

    published_policy_summary: str = Field(min_length=1, max_length=3000)
    policy_scope: Literal["comparable_policy", "related_guidance"] = "related_guidance"
    change_status: Literal["unverified", "supported", "contradicted", "conflicting"]
    change_summary: str = Field(min_length=1, max_length=1200)
    evidence_ids: list[str] = Field(default_factory=list, max_length=6)


class ScoringSummary(PipelineModel):
    """Explainable evidence indicators, never calibrated probabilities."""

    # Keep the legacy default when reading saved records without a version.
    version: Literal["evidence-v2", "evidence-v3", "evidence-v4"] = "evidence-v2"
    status: Literal["provisional", "evidence_based", "not_applicable", "plausibility_based"] | None = None
    evidence_strength: Literal["Insufficient", "Limited", "Moderate", "Strong"]
    supporting_strength: Confidence = 0
    contradicting_strength: Confidence = 0
    supporting_origins: int = Field(default=0, ge=0)
    contradicting_origins: int = Field(default=0, ge=0)
    reasons: list[str] = Field(min_length=1)


def _validate_scoring_contract(result, *, checkable=None):
    """Preserve legacy snapshots while enforcing the explicit v3 score meaning."""
    summary = result.scoring
    score = result.misinformation_risk_score
    label = result.concern_label
    outcome = result.assessment_outcome
    if (result.plausibility_context or outcome == "highly_unlikely") and (
            not summary or summary.version not in {"evidence-v3", "evidence-v4"} or summary.status != "plausibility_based"):
        raise ValueError("Climate plausibility requires an explicit versioned score status")
    if not summary or summary.version == "evidence-v2":
        if summary and summary.status is not None:
            raise ValueError("Scoring status requires evidence-v3 or later.")
        if label == "Not Enough Information" and score is not None:
            raise ValueError("Not Enough Information must have a null risk score in legacy results.")
        if label != "Not Enough Information" and score is None:
            raise ValueError("A concern assessment must include a risk score.")
        return
    if summary.status is None:
        raise ValueError("Versioned scoring requires an explicit scoring status.")
    if checkable is False and summary.status != "not_applicable":
        raise ValueError("A non-checkable result cannot have a factual risk score.")
    if checkable is True and summary.status == "not_applicable":
        raise ValueError("A completed factual check requires a risk score.")
    s, c = summary.supporting_strength, summary.contradicting_strength
    if summary.status == "plausibility_based":
        from .climate import OUTLIER_RISK
        if (outcome != "highly_unlikely" or label != "High Concern" or score != OUTLIER_RISK
                or not result.plausibility_context or summary.evidence_strength != "Limited"
                or s or c or summary.supporting_origins or summary.contradicting_origins):
            raise ValueError("A plausibility indicator needs its own grounded context, not decisive evidence votes")
        return
    if result.plausibility_context or outcome == "highly_unlikely":
        raise ValueError("Climate plausibility requires the matching score status")
    if summary.status in {"provisional", "not_applicable"}:
        if label != "Not Enough Information" or summary.evidence_strength != "Insufficient":
            raise ValueError("Unresolved or non-factual scores cannot claim a decisive finding.")
        if s or c or summary.supporting_origins or summary.contradicting_origins:
            raise ValueError("Provisional and non-applicable scores require zero decisive evidence.")
        if summary.status == "provisional":
            expected = 50 if summary.version == "evidence-v3" else None
            if score != expected or outcome not in {"insufficient_evidence", "unsupported"}:
                raise ValueError("Unresolved results require a null score in v4; only legacy v3 records retain 50.")
        elif score is not None or outcome != "not_checkable":
            raise ValueError("A non-applicable score must be null with a non-checkable outcome.")
        return
    expected_outcome = ("conflicting" if s and c else "supported" if s else
                        "contradicted" if c else None)
    labels = {"supported": "Low Concern", "contradicted": "High Concern", "conflicting": "Needs Caution"}
    if outcome != expected_outcome or expected_outcome is None or label != labels[expected_outcome]:
        raise ValueError("An evidence-based score requires a matching decisive evidence outcome.")
    if bool(s) != bool(summary.supporting_origins) or bool(c) != bool(summary.contradicting_origins):
        raise ValueError("Evidence strengths and source-origin counts must agree.")
    if summary.evidence_strength == "Insufficient" or score != round(round(50 * (1 - s + c), 8)):
        raise ValueError("The evidence-based score must match the recorded evidence strengths.")


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
    scoring: ScoringSummary | None = None
    component_assessment: ComponentAssessment | None = None
    policy_context: PolicyContext | None = None
    forecast_context: ForecastContext | None = None
    plausibility_context: PlausibilityContext | None = None
    claim_comparisons: list[ClaimComparison] = Field(default_factory=list, max_length=37)

    @model_validator(mode="after")
    def validate_score_and_label(self) -> "AssessmentResult":
        _validate_scoring_contract(self)
        validate_component_result(self)
        evidence_ids = [item.evidence_id for item in self.assessed_evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("Assessed evidence IDs must be unique.")
        if self.plausibility_context and self.plausibility_context.evidence_id not in evidence_ids:
            raise ValueError("Plausibility context must cite assessed evidence")
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
    forecast: ForecastData | None = None
    climate_record: ClimateRecord | None = None


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
    scoring: ScoringSummary | None = None
    component_assessment: ComponentAssessment | None = None
    credibility: CredibilityRating | None = None
    policy_context: PolicyContext | None = None
    forecast_context: ForecastContext | None = None
    plausibility_context: PlausibilityContext | None = None
    claim_context: ClaimContext | None = None
    claim_comparisons: list[ClaimComparison] = Field(default_factory=list, max_length=37)
    date_context: DateContext | None = None
    warnings: list[str] = Field(default_factory=list)
    pipeline_version: str = Field(min_length=1)
    created_at: datetime

    @model_validator(mode="after")
    def validate_final_result(self) -> "TextAnalysisResult":
        _validate_claim_context(self.extracted_claim, self.claim_context, self.date_context)
        _validate_scoring_contract(self, checkable=self.checkable)
        if self.credibility is not None and self.credibility != build_credibility(self):
            raise ValueError("Credibility rating must match the recorded evidence and outcome.")
        if self.checkable and not self.extracted_claim:
            raise ValueError(
                "A checkable result must include extracted_claim."
            )
        sources = {item.evidence_id: item for item in self.evidence}
        validate_component_result(self, self.extracted_claim or "", sources)
        if self.policy_context and any(key not in sources for key in self.policy_context.evidence_ids):
            raise ValueError("Policy context must cite returned evidence")
        if self.forecast_context and any(key not in sources for key in self.forecast_context.evidence_ids):
            raise ValueError("Forecast context must cite returned evidence")
        if self.plausibility_context:
            from .climate import RECORD_URL, render_record, eligible, MAX_REFERENCE_AGE
            context = self.plausibility_context
            source = sources.get(context.evidence_id)
            if (not source or str(source.url) != RECORD_URL or source.climate_record != context.record
                    or source.passage != render_record(context.record) or source.stance != "neutral"
                    or not eligible(self.claim_context, self.date_context)
                    or not 0 <= (self.claim_context.as_of - context.record.updated_at).days <= MAX_REFERENCE_AGE.days):
                raise ValueError("Plausibility context requires applicable official climate evidence")
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
