"""Default runtime dependencies for the text pipeline.

Only input preparation is implemented on ``main`` at present. Missing teammate
components raise explicit service errors instead of returning synthetic or
hard-coded misinformation assessments.
"""

from functools import lru_cache
from typing import NoReturn

from app.pipeline.input_preparation.service import prepare_text
from app.pipeline.orchestration.repository import FirestoreResultRepository
from app.pipeline.orchestration.service import PipelineOrchestrator
from app.pipeline.shared.errors import PipelineComponentError
from app.pipeline.shared.models import (
    ClaimAnalysis,
    PreparedText,
    RetrievalResult,
)


def _claim_analysis_not_ready(prepared: PreparedText) -> NoReturn:
    del prepared
    raise PipelineComponentError(
        "Claim analysis has not been integrated yet.",
        error_code="CLAIM_ANALYSIS_NOT_READY",
        stage="claim_analysis",
        retryable=False,
    )


def _retrieval_not_ready(claim: ClaimAnalysis) -> NoReturn:
    del claim
    raise PipelineComponentError(
        "Evidence retrieval has not been integrated yet.",
        error_code="EVIDENCE_RETRIEVAL_NOT_READY",
        stage="evidence_retrieval",
        retryable=False,
    )


def _assessment_not_ready(
    claim: ClaimAnalysis,
    retrieval: RetrievalResult,
) -> NoReturn:
    del claim, retrieval
    raise PipelineComponentError(
        "Evidence assessment has not been integrated yet.",
        error_code="EVIDENCE_ASSESSMENT_NOT_READY",
        stage="evidence_assessment",
        retryable=False,
    )


@lru_cache
def get_pipeline_orchestrator() -> PipelineOrchestrator:
    """Return the application pipeline used by the FastAPI dependency."""
    return PipelineOrchestrator(
        prepare_input=prepare_text,
        analyze_claim=_claim_analysis_not_ready,
        retrieve_evidence=_retrieval_not_ready,
        assess_evidence=_assessment_not_ready,
        repository=FirestoreResultRepository(),
    )

