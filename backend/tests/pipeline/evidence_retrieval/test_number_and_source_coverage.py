import asyncio
import json

import httpx
import pytest

from app.pipeline.evidence_retrieval import service
from app.pipeline.evidence_retrieval.sources import canonical_url, source_details


@pytest.mark.parametrize("plain,formatted", [("20000", "20,000"), ("1500000", "1,500,000"),
                                           ("20000.50", "20,000.50")])
def test_grouping_separators_do_not_change_retrieval_tokens(plain, formatted):
    assert service._tokens(f"The allowance is {plain} baht") == service._tokens(f"The allowance is {formatted} baht")


def test_different_amounts_remain_different():
    assert service._tokens("20,000 baht") != service._tokens("2,000 baht")
    assert service._tokens("200,00 baht") != service._tokens("20,000 baht")


@pytest.mark.parametrize("url", ["https://mfa.go.th/en/visa", "https://image.mfa.go.th/document.pdf",
                                "https://doha.thaiembassy.org/en/visa"])
def test_reviewed_thai_official_sources_are_allowed(url):
    assert canonical_url(url) == url
    assert source_details(url)[1] == "government"


@pytest.mark.parametrize("url", ["https://thaiembassy.org.evil.example/visa",
    "https://fakethaiembassy.org/visa", "https://mfa.go.th.evil.example/visa",
    "https://thaiembassy.com/visa", "https://user:pass@thaiembassy.org/visa"])
def test_similar_names_do_not_inherit_official_status(url):
    with pytest.raises(ValueError):
        canonical_url(url)


def test_first_person_wording_does_not_discard_a_relevant_entry_requirement():
    claim = "I need to have 20000 baht in cash to enter phuket"
    passage = ("Travellers entering Thailand under the Tourist Visa Exemption Scheme "
               "must possess adequate cash of or equivalent to 20,000 Baht per person or 40,000 Baht per family.")
    def handler(request):
        if request.url.host == "factchecktools.googleapis.com":
            return httpx.Response(200, json={})
        payload = json.loads(request.content)
        assert "mfa.go.th" in payload["include_domains"]
        assert "thaiembassy.org" in payload["include_domains"]
        return httpx.Response(200, json={"results": [{
            "url": "https://doha.thaiembassy.org/en/visa", "title": "Visa exemption",
            "content": passage, "score": 0.9,
        }]})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await service._retrieve_with_client(claim, client, "test-google", "test-tavily")
    result = asyncio.run(run())
    assert result.retrieval_status == "completed"
    assert result.evidence[0].passage == passage
    assert "Visa Exemption Scheme" in result.evidence[0].passage
