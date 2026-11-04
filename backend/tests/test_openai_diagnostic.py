"""The live diagnostic must report only safe metadata and never use app storage."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.pipeline.shared.errors import PipelineComponentError


SPEC = importlib.util.spec_from_file_location(
    "check_openai_assessment", Path(__file__).resolve().parents[1] / "scripts" / "check_openai_assessment.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class Result:
    def __init__(self, decisions=(), *, searches=0, research=None):
        self.decisions = list(decisions)
        self.searches = searches
        self.research = research

    def model_dump(self, **kwargs):
        return {"assessment_outcome": "supported", "credibility": {"label": "Evidence suggests this is true"},
                "explanation": "The cited evidence supports the message.", "pipeline_version": "experiment",
                "retrieval_trace": {"decisions": self.decisions, "search_requests": self.searches},
                "research_assessment": self.research,
                "user_id": "PRIVATE_USER", "original_text": "PRIVATE_INPUT", "evidence": ["PRIVATE_SOURCE"]}


def test_summary_reports_actual_responses_and_only_allowed_metadata():
    result = Result([
        {"decision": "verification_provider_selected", "provider": "openai", "model": "test-model"},
        {"decision": "verification_provider_usage", "provider": "openai", "model": "test-model",
         "input_tokens": "100", "output_tokens": "25", "total_tokens": "125", "extra": "PRIVATE_HEADER"},
        {"decision": "verification_provider_usage", "provider": "openai", "model": "test-model",
         "input_tokens": "200", "output_tokens": "30", "total_tokens": "230"},
        {"decision": "verification_contract_failure", "reason": "PRIVATE_PROVIDER_PAYLOAD"},
    ])
    output = runner.result_summary(result)
    assert output["openai_response_count"] == 2
    assert output["openai_models"] == ["test-model"]
    assert output["openai_token_usage"] == {"input_tokens": 300, "output_tokens": 55, "total_tokens": 355}
    assert output["billable_search_requests"] is None
    assert "PRIVATE_" not in json.dumps(output)


def test_selection_alone_is_not_reported_as_a_completed_response():
    output = runner.result_summary(Result([
        {"decision": "verification_provider_selected", "provider": "openai", "model": "test-model"},
    ]))
    assert output["openai_selected"] is True
    assert output["openai_response_count"] == 0
    assert output["openai_token_usage"] is None
    assert "no completed response" in output["assessment_note"]


def test_specialist_result_is_not_misreported_as_openai():
    output = runner.result_summary(Result())
    assert output["openai_selected"] is False
    assert output["openai_response_count"] == 0
    assert "did not use" in output["assessment_note"]


def test_preflight_never_switches_a_configured_ollama_provider(monkeypatch):
    monkeypatch.setenv("TEXT_ANALYSIS_MODE", "pipeline")
    monkeypatch.setenv("EVIDENCE_PIPELINE_V3", "1")
    monkeypatch.setenv("EVIDENCE_VERIFICATION_ENABLED", "true")
    monkeypatch.setenv("EVIDENCE_VERIFICATION_PROVIDER", "ollama")
    monkeypatch.setattr(runner, "_make_pipeline", lambda: pytest.fail("must not build pipeline"))
    output, code = runner.run_check("The museum opens at nine.")
    assert code == 1
    assert output["error_code"] == "EXPERIMENT_CONFIGURATION_INVALID"
    import os
    assert os.environ["EVIDENCE_VERIFICATION_PROVIDER"] == "ollama"


def test_openai_web_preflight_does_not_require_or_mutate_legacy_verification(monkeypatch):
    import os
    monkeypatch.setenv("TEXT_ANALYSIS_MODE", "openai_web")
    monkeypatch.setenv("EVIDENCE_PIPELINE_V3", "0")
    monkeypatch.setenv("EVIDENCE_VERIFICATION_ENABLED", "false")
    monkeypatch.setenv("EVIDENCE_VERIFICATION_PROVIDER", "ollama")
    monkeypatch.setenv("OPENAI_API_KEY", "private-diagnostic-test-key")
    monkeypatch.setenv("OPENAI_ASSESSMENT_MODEL", "test-model")
    settings = runner._preflight()
    assert settings.model == "test-model"
    assert os.environ["EVIDENCE_VERIFICATION_PROVIDER"] == "ollama"
    assert os.environ["EVIDENCE_VERIFICATION_ENABLED"] == "false"


def test_openai_web_preflight_requires_its_key_without_printing_provider_data(monkeypatch):
    monkeypatch.setenv("TEXT_ANALYSIS_MODE", "openai_web")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(runner, "_make_pipeline", lambda: pytest.fail("must not build pipeline"))
    output, code = runner.run_check("The museum opens at nine.")
    assert code == 1 and output["error_code"] == "OPENAI_NOT_CONFIGURED"
    assert output["saved_to_firebase"] is False and output["app_allowance_used"] is False


def test_openai_web_diagnostic_reports_both_phases_and_native_searches():
    result = Result([
        {"decision": "openai_web_research_selected", "provider": "openai", "model": "test-model"},
        {"decision": "openai_web_research_usage", "provider": "openai", "model": "test-model",
         "phase": "research", "input_tokens": "100", "output_tokens": "25", "total_tokens": "125",
         "billable_search_requests": "3", "extra": "PRIVATE_RESPONSE"},
        {"decision": "web_search_completed", "provider": "openai", "count": "4", "search_count": "2"},
        {"decision": "openai_web_research_usage", "provider": "openai", "model": "test-model",
         "phase": "formatting", "input_tokens": "200", "output_tokens": "30", "total_tokens": "230"},
    ], searches=2, research={
        "verdict": "likely_false", "research_text": "PRIVATE_RAW_RESEARCH",
        "sources": [{"title": "Official admission", "url": "https://example.gov.sg/admission",
                     "internal": "PRIVATE_SOURCE_METADATA"}],
    })
    output = runner.result_summary(result)
    assert output["openai_selected"] is True and output["openai_response_count"] == 2
    assert output["openai_models"] == ["test-model"]
    assert output["openai_token_usage"] == {"input_tokens": 300, "output_tokens": 55, "total_tokens": 355}
    assert output["web_search_calls"] == 2
    assert output["billable_search_requests"] == 3
    assert output["research_verdict"] == "likely_false"
    assert output["research_sources"] == [{"title": "Official admission", "url": "https://example.gov.sg/admission"}]
    assert "PRIVATE_" not in json.dumps(output)


def test_diagnostic_billable_searches_use_only_nonnegative_counts():
    output = runner.result_summary(Result([
        {"decision": "openai_web_research_usage", "provider": "openai", "model": "test-model",
         "billable_search_requests": value}
        for value in ["2", 3, -1, True, "PRIVATE_INVALID_COUNT", None]
    ]))
    assert output["billable_search_requests"] == 5
    assert "PRIVATE_" not in json.dumps(output)


def test_diagnostic_replaces_firestore_storage_and_monitoring(monkeypatch):
    from app.pipeline.orchestration import dependencies
    from app.pipeline.orchestration.repository import InMemoryResultRepository
    captured = {}
    class Pipeline:
        def with_repository(self, repository, *, run_recorder):
            captured.update(repository=repository, run_recorder=run_recorder)
            return self
    fake = Pipeline()
    monkeypatch.setattr(dependencies, "get_pipeline_orchestrator", lambda: fake)
    assert runner._make_pipeline() is fake
    assert isinstance(captured["repository"], InMemoryResultRepository)
    assert captured["run_recorder"]({"status": "failed"}) is None


def test_unknown_error_does_not_print_exception_payload(monkeypatch):
    monkeypatch.setattr(runner, "_preflight", lambda: SimpleNamespace(model="test-model"))
    def fail():
        raise RuntimeError("PRIVATE_PROVIDER_KEY and raw response")
    monkeypatch.setattr(runner, "_make_pipeline", fail)
    output, code = runner.run_check("The museum opens at nine.")
    assert code == 1
    assert output["error_code"] == "DIAGNOSTIC_FAILED"
    assert "PRIVATE_" not in json.dumps(output)


def test_safe_pipeline_error_reports_stage_without_raw_context(monkeypatch):
    monkeypatch.setattr(runner, "_preflight", lambda: SimpleNamespace(model="test-model"))
    class Pipeline:
        def analyze(self, text):
            raise PipelineComponentError("The provider is unavailable.", error_code="OPENAI_UNAVAILABLE",
                                         stage="evidence_assessment")
    monkeypatch.setattr(runner, "_make_pipeline", Pipeline)
    output, code = runner.run_check("The museum opens at nine.")
    assert code == 1
    assert output["stage"] == "evidence_assessment"
    assert output["app_allowance_used"] is False
    assert output["saved_to_firebase"] is False
