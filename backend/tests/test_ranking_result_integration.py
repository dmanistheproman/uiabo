"""A ranking finding retains scope, evidence gates and account history."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.pipeline.evidence_assessment import pool
from app.pipeline.input_preparation.service import prepare_text
from app.pipeline.orchestration.dependencies import get_pipeline_orchestrator
from app.pipeline.orchestration.repository import InMemoryResultRepository
from app.pipeline.orchestration.service import PipelineOrchestrator
from app.pipeline.shared.models import ClaimAnalysis, EvidenceCandidate, EvidenceProvenance, RetrievalResult

NOW = datetime(2026, 10, 5, 10, tzinfo=timezone.utc)
CLAIM = "Singapore prime minister is the highest paid politician"


def source(key, text, relevance="direct", applicability="established"):
    return EvidenceCandidate(evidence_id=key, title="Political salary comparison",
        url=f"https://www.bbc.com/news/{key}", publisher="BBC", source_type="news",
        retrieved_at=NOW, passage=text, retrieval_score=.9,
        provenance=EvidenceProvenance(source_policy="catalogue", source_reason="Reviewed publisher",
            origin_group="bbc", discovery_method="preferred_search", relevance=relevance,
            relevance_reason="Published political salary information", relevance_quote=text,
            applicability=applicability, applicability_reason="Same comparison" if applicability == "established" else "Old ranking"))


def test_ranking_scope_and_source_gates_survive_history(signed_analysis, monkeypatch):
    evidence = [source("comparison", "Singapore's prime minister is the highest-paid head of government by published annual salary."),
                source("old", "In 2020 Singapore topped the ranking.", applicability="uncertain_time"),
                source("figure", "The prime minister earns an annual salary.", relevance="context")]

    async def verdicts(text, sources):
        # Even a model's positive answers cannot promote a context-only source
        # or a ranking with unresolved dates into decisive votes.
        return {key: {"verdict": "supporting", "confidence": .9, "settles": .9, "quality": 4}
                for key, _ in sources}, "jev"
    monkeypatch.setattr(pool, "_pool_verdicts", verdicts)
    pipeline = PipelineOrchestrator(prepare_input=prepare_text,
        analyze_claim=lambda prepared: ClaimAnalysis(extracted_claim=prepared.normalised_text,
            claim_category="factual", checkable=True, claim_confidence=1, classification_reason="Ranking"),
        retrieve_evidence=lambda claim: RetrievalResult(retrieval_status="completed", evidence=evidence),
        assess_evidence=pool.assess_pool_evidence, repository=InMemoryResultRepository(), clock=lambda: NOW)
    app.dependency_overrides[get_pipeline_orchestrator] = lambda: pipeline
    with TestClient(app) as client:
        response = client.post("/analysis/text", json={"text": CLAIM}, headers={"Idempotency-Key": "ranking-test"})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["assessment_outcome"] == "supported"
        assert result["scoring"]["supporting_origins"] == 1
        assert [item["stance"] for item in result["evidence"]] == ["supporting", "neutral", "neutral"]
        assert "not personal wealth" in result["explanation"]
        assert "bonuses and allowances" in result["claim_context"]["assumptions"][0]
        saved = client.get("/analysis/results/" + result["result_id"]).json()
        history = client.get("/analysis/results").json()["results"][0]
        for item in [saved, history]:
            assert item["explanation"] == result["explanation"]
            assert item["claim_context"] == result["claim_context"]
            assert item["scoring"] == result["scoring"]


def test_salary_figure_or_old_ranking_alone_does_not_get_a_supported_score(monkeypatch):
    from app.pipeline.shared.context import build_claim_context
    claim = ClaimAnalysis(extracted_claim=CLAIM, claim_category="factual", checkable=True,
        claim_confidence=1, classification_reason="Ranking", claim_context=build_claim_context(CLAIM, NOW))
    async def verdicts(text, sources):
        return {key: {"verdict": "supporting", "confidence": 1, "settles": 1, "quality": 4}
                for key, _ in sources}, "jev"
    monkeypatch.setattr(pool, "_pool_verdicts", verdicts)
    for evidence in [source("figure", "Annual salary is S$2.2 million.", relevance="context"),
                     source("old", "The highest salary in 2000.", applicability="uncertain_time")]:
        result = pool.assess_pool_evidence(claim, RetrievalResult(retrieval_status="completed", evidence=[evidence]))
        assert result.assessment_outcome == "insufficient_evidence"
        assert result.scoring.status == "provisional"
