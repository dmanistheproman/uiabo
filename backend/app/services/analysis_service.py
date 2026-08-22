"""Compatibility wrapper for the Sprint 1 pipeline.

New code should inject ``PipelineOrchestrator`` through the FastAPI route. This
module remains so existing imports fail safely instead of returning the old
hard-coded score of 50.
"""

from app.pipeline.orchestration.dependencies import (
    get_pipeline_orchestrator,
)
from app.schemas import TextAnalysisResult


def analyse_text_content(
    text: str
) -> TextAnalysisResult:
    return get_pipeline_orchestrator().analyze(text)
