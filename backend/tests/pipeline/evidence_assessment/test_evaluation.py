import json

import pytest

from scripts.evaluate_stance import ROOT, metrics, validate_dataset


def test_seed_dataset_has_distinct_groups_and_explicit_provisional_provenance():
    data = json.loads((ROOT / "evaluation/datasets/stance_seed_v1.json").read_text(encoding="utf-8"))
    validate_dataset(data)
    assert len(data["cases"]) == 125
    assert all(case["review_status"] == "pending_team_review" for case in data["cases"])
    assert all(case.get("provenance") or case["kind"] == "synthetic_controlled_passage" for case in data["cases"])


def test_errors_and_false_reassurance_are_not_hidden_by_accuracy():
    rows = [
        {"expected_stance": "supporting", "prediction": "supporting"},
        {"expected_stance": "contradicting", "prediction": "supporting"},
        {"expected_stance": "neutral", "prediction": None},
    ]
    result = metrics(rows, "prediction")
    assert result["accuracy_including_errors"] == 0.3333
    assert result["technical_errors"] == 1
    assert result["false_support_count"] == 1
    assert result["decision_coverage"] == 0.6667
    assert result["accuracy_when_decisive"] == 0.5


def test_validation_rejects_group_leakage():
    data = json.loads((ROOT / "evaluation/datasets/stance_seed_v1.json").read_text(encoding="utf-8"))
    data["cases"][0]["split"] = "holdout"
    with pytest.raises(ValueError, match="crosses"):
        validate_dataset(data)
