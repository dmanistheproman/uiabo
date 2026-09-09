import json

from scripts.evaluate_retrieval import ROOT, summarise


def test_real_topic_dataset_preserves_pairs_and_reference_splits():
    data = json.loads((ROOT / "evaluation/datasets/retrieval_seed_v1.json").read_text(encoding="utf-8"))
    cases = data["cases"]
    assert len(cases) == 43
    assert len({case["id"] for case in cases}) == len(cases)
    assert all(case["review_status"] == "pending_two_human_reviewers" for case in cases)
    sources, groups = {}, {}
    for case in cases:
        groups.setdefault(case["group"], set()).add(case["split"])
        for url in case["reference_urls"]:
            sources.setdefault(url, set()).add(case["split"])
    assert all(len(splits) == 1 for splits in groups.values())
    assert all(len(splits) == 1 for splits in sources.values())


def test_report_counts_wrong_answers_and_errors_separately():
    cases = [{"runs": {"web": value}} for value in [
        {"outcome": "supported", "matches_provisional_label": False, "wrong_decisive": True,
         "duration_seconds": 10, "quote_integrity": True},
        {"error_code": "RETRIEVAL_UNAVAILABLE", "duration_seconds": 20},
        {"outcome": "insufficient", "matches_provisional_label": True, "wrong_decisive": False,
         "duration_seconds": 30, "quote_integrity": True}]]
    result = summarise(cases, ["web"])["web"]
    assert result["cases"] == 3
    assert result["wrong_decisive"] == 1
    assert result["errors"] == 1
    assert result["provisional_label_matches"] == 1
    assert result["mean_seconds"] == 20
