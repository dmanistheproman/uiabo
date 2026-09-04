from app.pipeline.evidence_retrieval.service import retrieve_evidence


TAX_CLAIM = {
    "extracted_claim": "A new $500 community tax starts next week.",
    "claim_category": "factual",
    "checkable": True,
    "classification_reason": (
        "This describes a specific public event "
        "that can be checked using public evidence."
    ),
    "claim_confidence": 0.86
}


def fake_successful_search(claim_text):
    return [
        {
            "evidence_id": "evidence-tax-1",
            "title": "Example agency clarification on community tax message",
            "url": "https://sources.example/agency/tax-clarification",
            "publisher": "Example Government Agency",
            "published_at": "2026-08-10",
            "passage": "No new $500 community tax will begin next week.",
            "source_type": "government",
            "retrieval_score": 0.93,
            "retrieved_at": "2026-08-20T10:00:00Z"
        },
        {
            "evidence_id": "evidence-tax-2",
            "title": "Example fact check about the community tax message",
            "url": "https://sources.example/fact-checks/community-tax",
            "publisher": "Example Fact Checker",
            "published_at": "2026-08-11",
            "passage": (
                "The circulating message about a new "
                "$500 community tax is incorrect."
            ),
            "source_type": "fact_check",
            "retrieval_score": 0.89,
            "retrieved_at": "2026-08-20T10:00:01Z"
        }
    ]


def test_retrieval_completed():
    result = retrieve_evidence(
        TAX_CLAIM,
        search_func=fake_successful_search
    )

    assert result["retrieval_status"] == "completed"
    assert len(result["evidence"]) == 2
    assert result["warnings"] == []
