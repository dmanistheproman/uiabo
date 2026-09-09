"""Default runtime dependencies for the text pipeline.

Input preparation, claim analysis, live evidence retrieval and assessment are connected.
"""

from functools import lru_cache

from app.pipeline.claim_analysis.service import analyse_claim
from app.pipeline.evidence_assessment.semantic import configured_assessor
from app.pipeline.evidence_retrieval.service import configured_retriever
from app.pipeline.input_preparation.service import prepare_text
from app.pipeline.orchestration.repository import FirestoreResultRepository
from app.pipeline.orchestration.service import PipelineOrchestrator


@lru_cache
def get_pipeline_orchestrator() -> PipelineOrchestrator:
    """Return the application pipeline used by the FastAPI dependency."""
    assessor, version = configured_assessor()
    retriever, retrieval_version = configured_retriever()
    return PipelineOrchestrator(
        prepare_input=prepare_text,
        analyze_claim=analyse_claim,
        retrieve_evidence=retriever,
        assess_evidence=assessor,
        pipeline_version=version + ":" + retrieval_version,
        repository=FirestoreResultRepository(),
    )
