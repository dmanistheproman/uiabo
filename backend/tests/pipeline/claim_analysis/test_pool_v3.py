"""pipeline-v3 claim-analysis tests: reconcile logic and provider chain."""

import asyncio
import json

import httpx
import pytest

from app.pipeline.claim_analysis import pool_v3
from app.pipeline.shared.errors import PipelineComponentError
from app.pipeline.shared.models import PreparedText


def prepared(text="Every household can claim S$800 in CDC vouchers this year."):
    return PreparedText(original_text=text, normalised_text=text, language="en",
                        warnings=[])


def test_reconcile_checkable_wins_over_choice():
    # choice said opinion but noul says a checkable assertion exists -> factual
    assert pool_v3.reconcile(0.91, "opinion") == ("factual", True, 0.91)
    assert pool_v3.reconcile(0.5, "joke_or_satire") == ("factual", True, 0.5)


def test_reconcile_veto_blocks_factual_label():
    # noul vetoes; a 'factual' choice must not surface as a checkable category
    category, checkable, confidence = pool_v3.reconcile(0.17, "factual")
    assert category == "unverifiable" and not checkable
    assert confidence == round(1.0 - 0.17, 2)
    # non-factual choice passes through
    assert pool_v3.reconcile(0.49, "opinion") == ("opinion", False, 0.51)


def test_question_with_factual_category_is_checkable():
    # a question may be a fact check or an opinion ask; measured noul draws
    # separate them (fact questions 0.73+, opinion asks <=0.53), so questions
    # use a higher bar than statements and ignore the (always-unverifiable)
    # category argmax for question forms.
    assert pool_v3.reconcile(0.73, "unverifiable", is_question=True) == ("factual", True, 0.73)
    assert pool_v3.reconcile(0.73, "opinion", is_question=True) == ("factual", True, 0.73)
    # opinion ask: below the question bar -> refused
    assert pool_v3.reconcile(0.53, "unverifiable", is_question=True) == ("unverifiable", False, 0.47)
    # injection / speculative draws stay refused
    assert pool_v3.reconcile(0.38, "unverifiable", is_question=True)[1] is False
    assert pool_v3.reconcile(0.16, "prediction", is_question=True) == ("prediction", False, 0.84)
    # statements keep the strict single-draw rule
    assert pool_v3.reconcile(0.38, "factual")[1] is False


def test_is_question_detection():
    assert pool_v3._is_question("is singapore airlines owned by the government?")
    assert pool_v3._is_question("Is it true that SIA is government owned")
    assert pool_v3._is_question("does the government own sia")
    assert not pool_v3._is_question("singapore airlines is owned by the government.")
    assert not pool_v3._is_question("Tap here to claim your prize! Send your bank details.")


def test_jev_classification_maps_answers(monkeypatch):
    body = {"answers": {"has_claim": {"noul": 0.93}, "cat": {"choice": "opinion"}}}
    seen = []
    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, json=body)
    async def request():
        async with httpx.AsyncClient(base_url="https://api.typesafe.ai",
                                     transport=httpx.MockTransport(handler)) as client:
            return await pool_v3._classify_jev(client, "jev-key", prepared())
    category, checkable, confidence = asyncio.run(request())
    assert (category, checkable) == ("factual", True)
    assert confidence == 0.93
    assert "typesafe.ai" in seen[0]


def test_classification_chain_falls_back_to_merged_oss(monkeypatch):
    seen = []
    merged = json.dumps({"claim_category": "factual", "category_confidence": 0.8,
                         "category_reason": "r",
                         "extracted_claim": "Every household can claim S$800 in CDC vouchers this year."})
    def handler(request):
        seen.append(str(request.url))
        if "typesafe.ai" in str(request.url):
            return httpx.Response(403)
        return httpx.Response(200, json={"done": True, "message": {"content": merged}})
    async def request():
        async with httpx.AsyncClient(base_url="https://ollama.com",
                                     transport=httpx.MockTransport(handler)) as client:
            return await pool_v3._classify_stage(prepared(), client, "jev-key", "oss-key")
    verdicts, span, provider = asyncio.run(request())
    assert provider == "oss-merged"
    assert verdicts[1] is True  # checkable from span presence
    assert span and "S$800" in span
    assert any("typesafe.ai" in url for url in seen)
    assert any("ollama.com" in url for url in seen)


def test_no_oss_key_raises(monkeypatch):
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    monkeypatch.setattr(pool_v3, "load_dotenv", lambda *a, **k: False)
    with pytest.raises(PipelineComponentError):
        pool_v3._keys()


def test_extraction_prompt_has_security_section():
    assert "UNTRUSTED DATA" in pool_v3.EXTRACTION_PROMPT
    assert "null" in pool_v3.EXTRACTION_PROMPT