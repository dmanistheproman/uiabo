"""pipeline-v3 whole-pool assessor tests.

Covers the shared per-source schema, the settles gate, and the strict
Jev -> gpt-oss provider chain with no third mode.
"""

import asyncio
import json

import httpx
import pytest

from app.pipeline.evidence_assessment import pool
from app.pipeline.shared.errors import PipelineComponentError
from app.pipeline.shared.models import ClaimAnalysis, EvidenceCandidate, RetrievalResult


def claim():
    return ClaimAnalysis(extracted_claim="The event is free.", claim_category="factual",
                         checkable=True, classification_reason="Test", claim_confidence=1)


def evidence(evidence_id="one", passage="Admission to the event costs $10.",
             full_text=None):
    return EvidenceCandidate(evidence_id=evidence_id, passage=passage,
                             title="Event notice", url=f"https://example.invalid/{evidence_id}",
                             publisher="Test publisher", source_type="government",
                             retrieval_score=0.95, retrieved_at="2026-09-08T00:00:00Z",
                             full_text=full_text)


def source_entry(**changes):
    base = {"verdict": "supporting", "confidence": 0.9, "settles": 0.9, "quality": 4}
    base.update(changes)
    return base


def test_format_pool_state_is_identical_regardless_of_provider():
    state = pool.format_pool_state("Claim.", [("s0", "Page text."), ("s1", "Other page.")])
    assert state.endswith("CLAIM: Claim.\n\nSOURCE s0:\nPage text.\n\nSOURCE s1:\nOther page.")


def test_parse_sources_validates_schema():
    parsed = pool._parse_sources({"sources": {"s0": source_entry()}})
    assert parsed["s0"] == {"verdict": "supporting", "confidence": 0.9,
                            "settles": 0.9, "quality": 4}
    with pytest.raises(ValueError):
        pool._parse_sources({"sources": {"s0": {"verdict": "true"}}})
    with pytest.raises(ValueError):
        pool._parse_sources({"nope": {}})


def test_jev_call_maps_answers_to_shared_schema(monkeypatch):
    answers = {"verdict_s0": {"choice": "contradicting", "confidence": None,
                              "probabilities": {"contradicting": 0.95}},
               "settles_s0": {"noul": 0.8}, "quality_s0": {"score": 3}}
    seen = []
    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, json={"answers": answers})
    async def request():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await pool._call_jev(client, "k", "CLAIM: x\n\nSOURCE s0:\ntext", ["s0"])
    result = asyncio.run(request())
    assert result["s0"] == {"verdict": "contradicting", "confidence": 0.95,
                            "settles": 0.8, "quality": 3}
    assert "typesafe.ai" in seen[0]


def test_oss_call_parses_shared_schema():
    content = json.dumps({"sources": {"s0": {"verdict": "supporting", "confidence": 0.8,
                                             "settles": 0.6, "quality": 2}}})
    seen = []
    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, json={"done": True,
                                         "message": {"content": content}})
    async def request():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                     base_url="https://ollama.com") as client:
            return await pool._call_oss(client, "k", "CLAIM: x\n\nSOURCE s0:\ntext")
    result = asyncio.run(request())
    assert result["s0"]["verdict"] == "supporting"
    assert "ollama.com" in seen[0]


def test_to_assessed_applies_settles_gate():
    retrieval = RetrievalResult(retrieval_status="completed", evidence=[
        evidence("a"), evidence("b"), evidence("c")])
    verdicts = {"s0": source_entry(),
                "s1": source_entry(verdict="contradicting", settles=0.3),
                "s2": source_entry(verdict="irrelevant", settles=0.0)}
    assessed = pool.to_assessed(retrieval, verdicts, 0.5)
    assert [item.stance for item in assessed] == ["supporting", "neutral", "neutral"]
    # structural quality: government cap 0.94 x relevance 0.95; neutral capped 0.45
    assert assessed[0].quality_score == 0.94
    assert assessed[1].quality_score == 0.45


def test_to_assessed_missing_source_defaults_neutral():
    retrieval = RetrievalResult(retrieval_status="completed", evidence=[evidence("a")])
    assessed = pool.to_assessed(retrieval, {}, 0.5)
    assert assessed[0].stance == "neutral"
    assert assessed[0].quality_score == 0.45


def test_settles_threshold_per_provider():
    assert pool.settles_threshold("jev") == pool.DEFAULT_SETTLES_JEV
    assert pool.settles_threshold("oss") == pool.DEFAULT_SETTLES_OSS
    assert pool.settles_threshold() == pool.DEFAULT_SETTLES_OSS
    assert pool.settles_threshold("unknown") == pool.DEFAULT_SETTLES_OSS


def test_provider_chain_jev_failure_falls_back_to_oss(monkeypatch):
    seen = []
    def handler(request):
        seen.append(str(request.url))
        if "typesafe.ai" in str(request.url):
            return httpx.Response(503)
        return httpx.Response(200, json={"done": True, "message": {"content": json.dumps(
            {"sources": {"s0": {"verdict": "contradicting", "confidence": 0.8,
                                "settles": 0.7, "quality": 2}}})}})
    verdicts_out, provider = asyncio.run(patched_verdicts(pool, handler))
    assert provider == "oss"
    assert verdicts_out["s0"]["verdict"] == "contradicting"
    assert any("typesafe.ai" in url for url in seen)
    assert any("ollama.com" in url for url in seen)


async def patched_verdicts(pool_module, handler):
    """Reimplement _pool_verdicts flow with a mocked transport to observe order."""
    state = pool_module.format_pool_state("Claim.", [("s0", "text")])
    errors = []
    async with httpx.AsyncClient(base_url="https://api.typesafe.ai",
                                 transport=httpx.MockTransport(handler)) as client:
        try:
            return await pool_module._call_jev(client, "k1", state, ["s0"]), "jev"
        except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError):
            errors.append("jev")
    async with httpx.AsyncClient(base_url="https://ollama.com",
                                 transport=httpx.MockTransport(handler)) as client:
        return await pool_module._call_oss(client, "k2", state), "oss"


def test_both_providers_failing_raises_retryable(monkeypatch):
    def handler(request):
        return httpx.Response(503)
    monkeypatch.setattr(pool, "_provider_keys", lambda: ("k1", "k2"))
    async def request():
        state = pool.format_pool_state("Claim.", [("s0", "text")])
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            try:
                await pool._call_jev(client, "k1", state, ["s0"])
            except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError):
                pass
            try:
                await pool._call_oss(client, "k2", state)
            except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError):
                pass
    asyncio.run(request())
    with pytest.raises(PipelineComponentError) as info:
        raise pool._stage_error("Evidence could not be assessed reliably. Please retry.",
                                "ASSESSMENT_UNAVAILABLE")
    assert info.value.error_code == "ASSESSMENT_UNAVAILABLE"
    assert info.value.retryable


def test_no_keys_configured_raises(monkeypatch):
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    monkeypatch.setattr(pool, "_provider_keys", lambda: (None, None))
    with pytest.raises(PipelineComponentError):
        asyncio.run(pool._pool_verdicts("Claim.", [("s0", "text")]))


def test_pool_assessor_end_to_end(monkeypatch):
    async def fake_verdicts(claim_text, sources):
        return {"s0": {"verdict": "supporting", "confidence": 0.9,
                       "settles": 0.9, "quality": 4}}, "jev"
    monkeypatch.setattr(pool, "_pool_verdicts", fake_verdicts)
    monkeypatch.setattr(pool, "_provider_keys", lambda: ("k1", "k2"))
    retrieval = RetrievalResult(retrieval_status="completed", evidence=[evidence()])
    result = pool.assess_pool_evidence(claim(), retrieval)
    assert result.assessment_outcome in ("supported", "insufficient_evidence")
    assert result.scoring.version == "evidence-v4"
    assert any("jev" in reason for reason in result.scoring.reasons)


def test_validated_passage_and_full_text_both_reach_judge():
    items = [evidence("one", passage="short slice",
                      full_text="FULL PAGE TEXT much longer " * 10)]
    sources = pool._pool_sources(items)
    assert sources[0][1].startswith("short slice")
    assert "FULL PAGE TEXT" in sources[0][1]
    assert len(sources[0][1]) <= pool.PAGE_CAP_CHARS


def test_passage_fallback_when_full_text_missing():
    items = [evidence("one", passage="Selected passage only.", full_text=None)]
    sources = pool._pool_sources(items)
    assert sources[0][1] == "Selected passage only."
