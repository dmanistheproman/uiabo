"""Default runtime dependencies for the text pipeline.

Input preparation, claim analysis, live evidence retrieval and assessment are connected.
"""

from functools import lru_cache

from app.pipeline.claim_analysis.service import analyse_claim
from app.pipeline.evidence_assessment.service import assess_evidence
from app.pipeline.evidence_retrieval.service import retrieve_evidence
from app.pipeline.input_preparation.service import prepare_text
from app.pipeline.orchestration.repository import FirestoreResultRepository
from app.pipeline.orchestration.service import PipelineOrchestrator


@lru_cache
def get_pipeline_orchestrator() -> PipelineOrchestrator:
    """Return the application pipeline used by the FastAPI dependency."""
    return PipelineOrchestrator(
        prepare_input=prepare_text,
        analyze_claim=analyse_claim,
        retrieve_evidence=retrieve_evidence,
        assess_evidence=assess_evidence,
        repository=FirestoreResultRepository(),
    )
