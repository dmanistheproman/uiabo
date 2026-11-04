"""Default runtime dependencies for the text pipeline.

Input preparation, claim analysis, live evidence retrieval and assessment are connected.
pipeline-v3 (EVIDENCE_PIPELINE_V3=1) swaps the claim-analysis ensemble for one merged
call and the per-slice assessor for one whole-pool call with a strict Jev -> gpt-oss
provider chain.
"""

from functools import lru_cache

from app.pipeline.claim_analysis.service import analyse_claim
from app.pipeline.evidence_assessment.semantic import configured_assessor
from app.pipeline.evidence_retrieval.service import configured_retriever
from app.pipeline.input_preparation.service import prepare_text
from app.pipeline.orchestration.repository import FirestoreResultRepository
from app.pipeline.orchestration.run_recorder import get_run_store
from app.pipeline.orchestration.service import PipelineOrchestrator


def _pool_v3_enabled() -> bool:
    # Process env only: uvicorn --env-file sets it for the running backend,
    # while tests (no --env-file) stay on the default pipeline and hermetic.
    import os
    return os.environ.get("EVIDENCE_PIPELINE_V3", "").strip().lower() in ("1", "true", "yes")


@lru_cache
def get_pipeline_orchestrator() -> PipelineOrchestrator:
    """Return the application pipeline used by the FastAPI dependency."""
    import os
    from app.pipeline.evidence_assessment.verification import selected_provider, provider_version
    from app.pipeline.shared.errors import PipelineComponentError
    mode = os.environ.get('TEXT_ANALYSIS_MODE', 'pipeline').strip().lower()
    if mode == 'openai_web':
        from .research import OpenAIResearchPipeline
        return OpenAIResearchPipeline(repository=FirestoreResultRepository(), run_recorder=get_run_store().record)
    if mode != 'pipeline':
        raise PipelineComponentError('The text analysis mode setting is invalid.',
            error_code='ASSESSMENT_CONFIGURATION_INVALID', stage='evidence_assessment', retryable=False)
    use_pool = _pool_v3_enabled()
    verification_enabled = os.environ.get('EVIDENCE_VERIFICATION_ENABLED', 'true').strip().lower() in {'1', 'true', 'yes'}
    if selected_provider() == 'openai' and (not use_pool or not verification_enabled):
        raise PipelineComponentError('OpenAI assessment requires the V3 verification pipeline to be enabled.',
            error_code='OPENAI_CONFIGURATION_INVALID', stage='evidence_assessment', retryable=False)
    if use_pool:
        from app.pipeline.claim_analysis.pool_v3 import analyse_claim_v3
        from app.pipeline.evidence_assessment.pool import configured_pool_assessor
        assessor, version = configured_pool_assessor()
        claim_analyser = analyse_claim_v3
    else:
        assessor, version = configured_assessor()
        claim_analyser = analyse_claim
    retriever, retrieval_version = configured_retriever()
    planner, repairer = None, None
    if use_pool and verification_enabled:
        from app.pipeline.claim_analysis.verification_plan import build_verification_plan
        from app.pipeline.evidence_retrieval.service import configured_repairer
        planner, repairer = build_verification_plan, configured_repairer()
        version += ":verification-enabled-v1" + provider_version()
    elif use_pool:
        version += ":verification-disabled"
    return PipelineOrchestrator(
        prepare_input=prepare_text,
        analyze_claim=claim_analyser,
        retrieve_evidence=retriever,
        assess_evidence=assessor,
        pipeline_version=version + ":" + retrieval_version + ":credibility-v2",
        repository=FirestoreResultRepository(),
        run_recorder=get_run_store().record,
        plan_verification=planner,
        repair_evidence=repairer,
    )
