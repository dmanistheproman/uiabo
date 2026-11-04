"""Keep wrong verdicts, avoidable abstention and technical failures distinct."""

from run_oracle import load_cases, summarise


def test_oracle_expected_categories_and_source_packs_validate():
    pack = load_cases()
    assert len(pack["cases"]) == 12
    assert {case["expected"] for case in pack["cases"]} == {"supported", "contradicted", "unresolved"}


def test_metrics_do_not_count_provider_errors_as_factual_abstention():
    results = [
        {"status": "completed", "expected": "supported", "observed": "supported"},
        {"status": "completed", "expected": "contradicted", "observed": "unresolved"},
        {"status": "completed", "expected": "unresolved", "observed": "unresolved"},
        {"status": "completed", "expected": "unresolved", "observed": "contradicted", "plan_status": "fallback"},
        {"status": "error", "expected": "supported"},
    ]
    value = summarise(results)
    assert value["attempted"] == 5
    assert value["completed"] == 4
    assert value["provider_or_contract_errors"] == 1
    assert value["matched_expected"] == 2
    assert value["answerable_completed"] == 2
    assert value["answerable_abstentions"] == 1
    assert value["unsupported_misinformation_verdicts"] == 1
    assert value["correct_unresolved"] == 1
    assert value["planner_fallbacks"] == 1


def test_empty_evaluation_has_no_invented_success_rate():
    value = summarise([])
    assert value["expected_match_rate_completed"] is None
    assert value["answerable_abstention_rate"] is None
