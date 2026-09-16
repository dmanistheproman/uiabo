"""Sprint 1 text-pipeline orchestration.

The orchestrator owns control flow, not the internal AI/retrieval algorithms.
Each teammate component is injected as a callable and validated against the
shared Pydantic contract before its output is used.
"""

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from app.pipeline.evidence_assessment.scoring import unscored_summary, provisional_summary
from app.pipeline.orchestration.repository import ResultRepository
from app.pipeline.shared.dates import infer_date_context, assumption_notice
from app.pipeline.shared.context import build_claim_context
from app.pipeline.shared.errors import (
    PipelineComponentError,
    PipelineContractError,
    PipelineError,
    PipelineValidationError,
)
from app.pipeline.shared.models import (
    AssessmentResult,
    AssessedEvidence,
    ClaimAnalysis,
    EvidenceCandidate,
    EvidenceItem,
    FailedAnalysisRecord,
    PreparedText,
    RetrievalResult,
    TextAnalysisResult,
)


PIPELINE_VERSION = "sprint-1-v1"

T = TypeVar("T", bound=BaseModel)

InputPreparer = Callable[[str], Any]
ClaimAnalyzer = Callable[[PreparedText], Any]
EvidenceRetriever = Callable[[ClaimAnalysis], Any]
EvidenceAssessor = Callable[[ClaimAnalysis, RetrievalResult], Any]


class PipelineOrchestrator:
    """Connect all Sprint 1 components and persist the final record."""

    def __init__(
        self,
        *,
        prepare_input: InputPreparer,
        analyze_claim: ClaimAnalyzer,
        retrieve_evidence: EvidenceRetriever,
        assess_evidence: EvidenceAssessor,
        repository: ResultRepository,
        id_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
        pipeline_version: str = PIPELINE_VERSION,
    ) -> None:
        self._prepare_input = prepare_input
        self._analyze_claim = analyze_claim
        self._retrieve_evidence = retrieve_evidence
        self._assess_evidence = assess_evidence
        self._repository = repository
        self._id_factory = id_factory or (lambda: str(uuid4()))
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._pipeline_version = pipeline_version

    def with_repository(self, repository: ResultRepository) -> "PipelineOrchestrator":
        """Give one authenticated request its own persistence boundary."""
        return PipelineOrchestrator(
            prepare_input=self._prepare_input, analyze_claim=self._analyze_claim,
            retrieve_evidence=self._retrieve_evidence, assess_evidence=self._assess_evidence,
            repository=repository, clock=self._clock, pipeline_version=self._pipeline_version)

    def analyze(self, text: str) -> TextAnalysisResult:
        """Run the complete text pipeline and save a completed result.

        A valid ``Not Enough Information`` result is returned for a
        non-checkable statement or a successful search with insufficient
        evidence. Technical failures raise ``PipelineError`` and never look
        like a normal misinformation assessment.
        """
        result_id = self._id_factory()
        created_at = self._clock()
        prepared: PreparedText | None = None
        warnings: list[str] = []

        try:
            prepared = self._run_input_preparation(text)
            warnings.extend(prepared.warnings)

            claim = self._run_component(
                stage="claim_analysis",
                component=self._analyze_claim,
                model=ClaimAnalysis,
                args=(prepared,),
            )
            # Own this assumption on the server; do not accept an LLM-invented
            # date or rewrite the quoted claim. Use one clock for the whole run.
            claim.date_context = (infer_date_context(claim.extracted_claim, created_at)
                                  if claim.checkable else None)
            claim.claim_context = (build_claim_context(claim.extracted_claim, created_at)
                                   if claim.checkable else None)

            retrieval: RetrievalResult | None = None
            if not claim.checkable:
                assessment = _non_checkable_assessment(claim)
            else:
                retrieval = self._run_component(
                    stage="evidence_retrieval",
                    component=self._retrieve_evidence,
                    model=RetrievalResult,
                    args=(claim,),
                )
                warnings.extend(retrieval.warnings)

                if retrieval.retrieval_status == "failed":
                    raise PipelineComponentError(
                        "Analysis could not be completed because evidence "
                        "search is temporarily unavailable.",
                        error_code="RETRIEVAL_UNAVAILABLE",
                        stage="evidence_retrieval",
                        retryable=True,
                    )

                if retrieval.retrieval_status == "no_evidence":
                    assessment = _no_evidence_assessment(retrieval)
                else:
                    assessment = self._run_component(
                        stage="evidence_assessment",
                        component=self._assess_evidence,
                        model=AssessmentResult,
                        args=(claim, retrieval),
                    )

            if claim.date_context and claim.date_context.basis != "explicit_date":
                assessment.uncertainty_reasons.append(assumption_notice(claim.date_context))
                if assessment.uncertainty == "Low":
                    assessment.uncertainty = "Medium"
            result = _assemble_result(
                result_id=result_id,
                created_at=created_at,
                pipeline_version=self._pipeline_version,
                prepared=prepared,
                claim=claim,
                retrieval=retrieval,
                assessment=assessment,
                warnings=_unique(warnings),
            )

            self._repository.save_result(result)
            return result

        except PipelineError as error:
            if prepared is not None:
                self._record_failure_best_effort(
                    result_id=result_id,
                    created_at=created_at,
                    original_text=prepared.original_text,
                    warnings=_unique(warnings),
                    error=error,
                )
            raise

    def _run_input_preparation(self, text: str) -> PreparedText:
        try:
            raw_result = self._prepare_input(text)
        except PipelineError:
            raise
        except Exception as error:
            if all(
                hasattr(error, attribute)
                for attribute in ("message", "error_code", "http_status")
            ):
                raise PipelineValidationError(
                    str(error.message),
                    error_code=str(error.error_code),
                    http_status=int(error.http_status),
                ) from error
            raise PipelineComponentError(
                "Input preparation could not be completed.",
                error_code="INPUT_PREPARATION_FAILED",
                stage="input_preparation",
            ) from error

        return _validate_component_output(
            PreparedText,
            raw_result,
            stage="input_preparation",
        )

    def _run_component(
        self,
        *,
        stage: str,
        component: Callable[..., Any],
        model: type[T],
        args: tuple[Any, ...],
    ) -> T:
        try:
            raw_result = component(*args)
        except PipelineError:
            raise
        except Exception as error:
            raise PipelineComponentError(
                f"The {stage.replace('_', ' ')} component failed.",
                error_code=f"{stage.upper()}_FAILED",
                stage=stage,
            ) from error

        return _validate_component_output(model, raw_result, stage=stage)

    def _record_failure_best_effort(
        self,
        *,
        result_id: str,
        created_at: datetime,
        original_text: str,
        warnings: list[str],
        error: PipelineError,
    ) -> None:
        failure = FailedAnalysisRecord(
            result_id=result_id,
            original_text=original_text,
            failure_stage=error.stage,
            error_code=error.error_code,
            message=error.message,
            retryable=error.retryable,
            warnings=warnings,
            pipeline_version=self._pipeline_version,
            created_at=created_at,
        )

        try:
            self._repository.save_failure(failure)
        except PipelineError:
            # Preserve the original component error. Storage logging is best
            # effort when the analysis itself has already failed.
            return


def _validate_component_output(
    model: type[T],
    value: Any,
    *,
    stage: str,
) -> T:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")

    try:
        return model.model_validate(value)
    except ValidationError as error:
        raise PipelineContractError(
            f"The {stage.replace('_', ' ')} output does not match the "
            "agreed interface.",
            stage=stage,
        ) from error


def _non_checkable_assessment(claim: ClaimAnalysis) -> AssessmentResult:
    category = claim.claim_category.replace("_", " ")
    return AssessmentResult(
        concern_label="Not Enough Information",
        misinformation_risk_score=None,
        assessment_outcome="not_checkable",
        scoring=unscored_summary("No checkable factual claim was identified; a misinformation score does not apply."),
        uncertainty="High",
        uncertainty_reasons=[
            "No objectively checkable factual claim was found."
        ],
        explanation=(
            f"This statement was classified as {category}, so it cannot be "
            "assessed as a factual misinformation claim."
        ),
        recommended_action=(
            "Treat this as non-factual content rather than a verified fact."
        ),
        assessed_evidence=[],
    )


def _no_evidence_assessment(
    retrieval: RetrievalResult,
) -> AssessmentResult:
    reasons = retrieval.warnings or [
        "No sufficiently relevant evidence was found."
    ]
    return AssessmentResult(
        concern_label="Not Enough Information",
        misinformation_risk_score=50,
        assessment_outcome="insufficient_evidence",
        scoring=provisional_summary("No sufficient evidence for a factual verdict was found."),
        uncertainty="High",
        uncertainty_reasons=reasons,
        explanation=(
            "There is not enough reliable evidence to assess this claim."
        ),
        recommended_action=(
            "Check an authoritative source before believing or forwarding "
            "this claim."
        ),
        assessed_evidence=[],
    )


def _assemble_result(
    *,
    result_id: str,
    created_at: datetime,
    pipeline_version: str,
    prepared: PreparedText,
    claim: ClaimAnalysis,
    retrieval: RetrievalResult | None,
    assessment: AssessmentResult,
    warnings: list[str],
) -> TextAnalysisResult:
    evidence = _combine_evidence(retrieval, assessment.assessed_evidence)

    return TextAnalysisResult(
        result_id=result_id,
        original_text=prepared.original_text,
        extracted_claim=claim.extracted_claim,
        claim_category=claim.claim_category,
        checkable=claim.checkable,
        concern_label=assessment.concern_label,
        misinformation_risk_score=assessment.misinformation_risk_score,
        scoring=assessment.scoring,
        policy_context=assessment.policy_context,
        forecast_context=assessment.forecast_context,
        claim_context=claim.claim_context,
        uncertainty=assessment.uncertainty,
        uncertainty_reasons=assessment.uncertainty_reasons,
        explanation=assessment.explanation,
        recommended_action=assessment.recommended_action,
        assessment_outcome=assessment.assessment_outcome or (
            "not_checkable" if not claim.checkable else {
                "Low Concern": "supported", "High Concern": "contradicted",
                "Needs Caution": "conflicting", "Not Enough Information": "insufficient_evidence",
            }[assessment.concern_label]),
        claim_comparisons=assessment.claim_comparisons,
        date_context=claim.date_context,
        evidence=evidence,
        warnings=warnings,
        pipeline_version=pipeline_version,
        created_at=created_at,
    )


def _combine_evidence(
    retrieval: RetrievalResult | None,
    assessments: list[AssessedEvidence],
) -> list[EvidenceItem]:
    if retrieval is None or retrieval.retrieval_status != "completed":
        if assessments:
            raise PipelineContractError(
                "Evidence was assessed even though retrieval was not "
                "completed.",
                stage="result_assembly",
            )
        return []

    candidates: dict[str, EvidenceCandidate] = {
        item.evidence_id: item for item in retrieval.evidence
    }
    assessed = {item.evidence_id: item for item in assessments}

    if candidates.keys() != assessed.keys():
        raise PipelineContractError(
            "Every retrieved evidence item must have exactly one assessment.",
            stage="result_assembly",
        )

    return [
        EvidenceItem(
            evidence_id=candidate.evidence_id,
            title=candidate.title,
            url=candidate.url,
            publisher=candidate.publisher,
            published_at=candidate.published_at,
            passage=candidate.passage,
            source_type=candidate.source_type,
            stance=assessed[candidate.evidence_id].stance,
            quality_score=assessed[candidate.evidence_id].quality_score,
            assessment_reason=assessed[candidate.evidence_id].assessment_reason,
            evidence_quote=assessed[candidate.evidence_id].evidence_quote,
            provenance=candidate.provenance,
            forecast=candidate.forecast,
        )
        for candidate in retrieval.evidence
    ]


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
