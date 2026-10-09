"""Exercise the production provider chain without credentials or network calls."""

import asyncio
from datetime import date
import json
from types import SimpleNamespace

import httpx
import pytest

from app.pipeline.evidence_assessment import pool
from app.pipeline.evidence_assessment import components as component_module
from app.pipeline.shared.components import decompose_claim
from app.pipeline.shared.errors import PipelineComponentError


def install_transport(monkeypatch, handler, *, keys=("test-jev", "test-oss")):
    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(pool, "_provider_keys", lambda: keys)
    monkeypatch.setattr(pool.httpx, "AsyncClient", lambda **kwargs: real_client(
        transport=transport, **kwargs))


@pytest.mark.parametrize("failure", ["http", "timeout", "transport", "invalid_json", "missing_fields"])
def test_actual_pool_chain_returns_retryable_error_when_both_providers_fail(monkeypatch, failure):
    seen = []

    def handler(request):
        seen.append(request.url.host)
        if failure == "http":
            return httpx.Response(503, json={"error": "provider unavailable"})
        if failure == "timeout":
            raise httpx.ReadTimeout("provider timed out", request=request)
        if failure == "transport":
            raise httpx.ConnectError("provider disconnected", request=request)
        if failure == "invalid_json":
            return httpx.Response(200, text="not JSON")
        return httpx.Response(200, json={"done": True})

    install_transport(monkeypatch, handler)
    with pytest.raises(PipelineComponentError) as raised:
        asyncio.run(pool._pool_verdicts("Officials are discussing a change.", [("s0", "Evidence.")]))

    error = raised.value
    assert seen == ["api.typesafe.ai", "ollama.com"]
    assert error.error_code == "ASSESSMENT_UNAVAILABLE"
    assert error.stage == "evidence_assessment"
    assert error.retryable is True
    assert error.http_status == 503
    assert error.__cause__ is None
    assert "test-jev" not in str(error)
    assert "test-oss" not in str(error)


def test_actual_pool_chain_falls_back_to_oss_using_same_evidence(monkeypatch):
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        if request.url.host == "api.typesafe.ai":
            return httpx.Response(503)
        return httpx.Response(200, json={"done": True, "message": {"content": json.dumps({
            "sources": {"s0": {"verdict": "not_decisive", "confidence": 0.9,
                                 "settles": 0.1, "quality": 2}}})}})

    install_transport(monkeypatch, handler)
    verdicts, provider = asyncio.run(pool._pool_verdicts(
        "Officials are discussing a change.", [("s0", "Evidence does not establish a discussion.")]))

    assert provider == "oss"
    assert verdicts["s0"]["verdict"] == "not_decisive"
    assert requests[1]["messages"][0]["content"].startswith(requests[0]["state"])


def test_no_credentials_returns_retryable_failure_without_making_requests(monkeypatch):
    def handler(request):
        pytest.fail("Provider called without configured credentials")

    install_transport(monkeypatch, handler, keys=(None, None))
    with pytest.raises(PipelineComponentError) as raised:
        asyncio.run(pool._pool_verdicts("Claim.", [("s0", "Evidence.")]))
    assert raised.value.error_code == "ASSESSMENT_UNAVAILABLE"
    assert raised.value.retryable is True


def component_inputs():
    text = "The council is closing the bridge because inspectors found severe structural damage."
    claim = SimpleNamespace(extracted_claim=text, claim_context=SimpleNamespace(as_of=date(2026, 10, 8)))
    evidence = [SimpleNamespace(evidence_id="test", publisher="Synthetic authority", published_at=date(2026, 10, 8),
        passage="The published inspection identifies severe structural damage.", provenance=None)]
    return claim, decompose_claim(text), evidence


def component_oss_response(*, omit_pair=None):
    values = {f"{part}_s0": {"stance": "unresolved", "basis": "none", "scope": "unknown",
        "decisiveness": 0.1, "explanation": "The source does not establish this component."}
        for part in ("event", "premise", "causal_link")}
    if omit_pair:
        del values[omit_pair]
    return httpx.Response(200, json={"done": True, "message": {"content": json.dumps(values)}})


def component_jev_response(*, inference=False):
    answers = {}
    for part in ("event", "premise", "causal_link"):
        pair = f"{part}_s0"
        active = inference and part == "premise"
        answers[f"{pair}_stance"] = {"choice": "contradicting" if active else "unresolved"}
        answers[f"{pair}_scope"] = {"choice": "established" if active else "unknown"}
        answers[f"{pair}_basis"] = {"choice": "inference" if active else "none"}
        answers[f"{pair}_decisiveness"] = {"noul": .8 if active else .1}
    return httpx.Response(200, json={"answers": answers})


def test_component_actual_chain_malformed_jev_falls_back_to_oss_with_same_state(monkeypatch):
    seen = []

    def handler(request):
        seen.append((request.url.host, json.loads(request.content)))
        if request.url.host == "api.typesafe.ai":
            return httpx.Response(200, json={"answers": {"premise_s0_stance": {"choice": "contradicting"}}})
        return component_oss_response()

    install_transport(monkeypatch, handler)
    drafts, provider = asyncio.run(component_module.judge_components(*component_inputs()))
    assert provider == "oss"
    assert len(drafts) == 3
    assert [host for host, _ in seen] == ["api.typesafe.ai", "ollama.com"]
    assert seen[0][1]["state"] == seen[1][1]["messages"][1]["content"]


@pytest.mark.parametrize("failure", ["http", "incomplete_oss", "timeout"])
def test_component_actual_chain_fails_retryably_instead_of_inventing_findings(monkeypatch, failure):
    seen = []

    def handler(request):
        seen.append(request.url.host)
        if failure == "timeout":
            raise httpx.ReadTimeout("Synthetic timeout", request=request)
        if failure == "incomplete_oss" and request.url.host == "ollama.com":
            return component_oss_response(omit_pair="causal_link_s0")
        return httpx.Response(503)

    install_transport(monkeypatch, handler)
    with pytest.raises(PipelineComponentError) as raised:
        asyncio.run(component_module.judge_components(*component_inputs()))
    assert seen == ["api.typesafe.ai", "ollama.com"]
    assert raised.value.error_code == "ASSESSMENT_UNAVAILABLE"
    assert raised.value.stage == "evidence_assessment"
    assert raised.value.retryable is True


def test_jev_inference_requires_fallback_reasoning_and_does_not_survive_oss_disagreement(monkeypatch):
    seen = []

    def handler(request):
        seen.append(request.url.host)
        if request.url.host == "api.typesafe.ai":
            return component_jev_response(inference=True)
        return component_oss_response()

    install_transport(monkeypatch, handler)
    drafts, provider = asyncio.run(component_module.judge_components(*component_inputs()))
    assert seen == ["api.typesafe.ai", "ollama.com"]
    assert provider == "oss"
    assert drafts["premise_s0"].stance == "unresolved"
    assert drafts["premise_s0"].basis == "none"


def test_jev_inference_without_reasoning_provider_is_retryable_failure(monkeypatch):
    seen = []

    def handler(request):
        seen.append(request.url.host)
        return component_jev_response(inference=True)

    install_transport(monkeypatch, handler, keys=("test-jev", None))
    with pytest.raises(PipelineComponentError) as raised:
        asyncio.run(component_module.judge_components(*component_inputs()))
    assert seen == ["api.typesafe.ai"]
    assert raised.value.error_code == "ASSESSMENT_UNAVAILABLE"
    assert raised.value.retryable is True


def test_component_oversized_passage_does_not_call_providers_or_silently_truncate(monkeypatch):
    def handler(request):
        pytest.fail("Oversized source should be rejected before provider calls")

    install_transport(monkeypatch, handler)
    value, parts, evidence = component_inputs()
    evidence[0].passage = "x" * 12001
    with pytest.raises(PipelineComponentError) as raised:
        asyncio.run(component_module.judge_components(value, parts, evidence))
    assert raised.value.error_code == "ASSESSMENT_INPUT_TOO_LARGE"
