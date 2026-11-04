"""Synthetic evidence-pack regression runner; network use requires --live."""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import sys
import time


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PACK = HERE / "oracle_cases.json"
EXPECTED = {"supported", "contradicted", "unresolved", "conflicting"}


def load_cases(path=PACK):
    pack = json.loads(Path(path).read_text(encoding="utf-8"))
    if not pack.get("notice") or not pack.get("as_of"):
        raise ValueError("A synthetic pack needs its notice and assessment date.")
    cases = pack["cases"]
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Case IDs must be unique.")
    for case in cases:
        if case["expected"] not in EXPECTED or not case.get("reason"):
            raise ValueError("Each case needs an approved expected finding and justification.")
        if not 1 <= len(case["claim"]) <= 5000:
            raise ValueError("Invalid claim length.")
        if not case.get("sources"):
            raise ValueError("An oracle case needs a supplied source pack.")
        source_ids = [source["id"] for source in case["sources"]]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Source IDs must be unique within each case.")
        for source in case["sources"]:
            if not source.get("passage") or not source.get("title"):
                raise ValueError("Oracle sources need quoted content and a title.")
    return pack


def outcome_category(outcome):
    if outcome == "supported":
        return "supported"
    if outcome in {"contradicted", "likely_misinformation", "highly_unlikely"}:
        return "contradicted"
    if outcome == "conflicting":
        return "conflicting"
    return "unresolved"


def summarise(results):
    """Keep provider failures, justified abstentions and verdict errors separate."""
    completed = [item for item in results if item.get("status") == "completed"]
    answerable = [item for item in completed if item["expected"] != "unresolved"]
    expected_unknown = [item for item in completed if item["expected"] == "unresolved"]
    decisive = [item for item in completed if item["observed"] != "unresolved"]
    correct = sum(item["observed"] == item["expected"] for item in completed)
    abstentions = sum(item["observed"] == "unresolved" for item in answerable)
    unsupported_false = sum(item["observed"] == "contradicted" and item["expected"] != "contradicted" for item in completed)
    rate = lambda numerator, denominator: round(numerator / denominator, 4) if denominator else None
    return {
        "attempted": len(results), "completed": len(completed),
        "provider_or_contract_errors": len(results) - len(completed),
        "matched_expected": correct,
        "expected_match_rate_completed": rate(correct, len(completed)),
        "expected_match_rate_all_attempted": rate(correct, len(results)),
        "answerable_completed": len(answerable),
        "answerable_abstentions": abstentions,
        "answerable_abstention_rate": rate(abstentions, len(answerable)),
        "correct_decisive_findings": sum(item["observed"] == item["expected"] for item in decisive),
        "decisive_findings": len(decisive),
        "unsupported_misinformation_verdicts": unsupported_false,
        "expected_unresolved_completed": len(expected_unknown),
        "correct_unresolved": sum(item["observed"] == "unresolved" for item in expected_unknown),
        "planner_fallbacks": sum(item.get("plan_status") == "fallback" for item in results),
        "observed_counts": dict(Counter(item["observed"] for item in completed)),
    }


def make_inputs(case, as_of):
    from app.pipeline.shared.context import build_claim_context
    from app.pipeline.shared.dates import infer_date_context
    from app.pipeline.shared.models import ClaimAnalysis, EvidenceCandidate, EvidenceProvenance, RetrievalResult, RetrievalTrace

    claim = ClaimAnalysis(
        extracted_claim=case["claim"], checkable=True, claim_category="factual",
        classification_reason="Synthetic oracle fixture: the supplied statement is the evaluation input.",
        claim_confidence=1.0,
        claim_context=build_claim_context(case["claim"], as_of, original_text=case["claim"]),
        date_context=infer_date_context(case["claim"], as_of),
    )
    def fixture_provenance(source):
        if not source.get("applicability"):
            return None
        return EvidenceProvenance(
            source_policy="scoped_first_party", origin_group="synthetic-oracle",
            source_reason="Synthetic metadata only; this does not assert trust in a real publisher.",
            discovery_method="source_link", relevance="context",
            relevance_reason="The fixture supplies one link in a potentially combined proof.",
            relevance_quote=source["passage"][:1800], applicability=source["applicability"],
            applicability_reason="This individual passage does not establish the entire claim by itself.",
        )
    sources = [EvidenceCandidate(
        evidence_id=source["id"], title=source["title"],
        url=f"https://evidence.example/{case['id']}/{source['id']}",
        publisher="Fictional oracle source: " + source["title"],
        published_at=source.get("published_at"), passage=source["passage"],
        source_type="government", retrieval_score=0.8, retrieved_at=as_of,
        provenance=fixture_provenance(source),
    ) for source in case["sources"]]
    # These deliberately supplied documents have not passed live web selection.
    # Do not fabricate retrieval coverage or official-announcement search traces.
    return claim, RetrievalResult(retrieval_status="completed", evidence=sources, trace=RetrievalTrace())


def run_case(case, as_of):
    from app.pipeline.claim_analysis.verification_plan import build_verification_plan
    from app.pipeline.evidence_assessment.verification import assess_verification
    from app.pipeline.shared.verification import validate_verification_provenance

    started = time.perf_counter()
    row = {"id": case["id"], "pattern": case["pattern"], "claim": case["claim"], "expected": case["expected"]}
    try:
        claim, retrieval = make_inputs(case, as_of)
        plan = build_verification_plan(claim, original_text=case["claim"])
        claim.verification_plan = plan
        row.update(plan_status=plan.status, fallback_reason=plan.fallback_reason, plan=plan.model_dump(mode="json"))
        result = asyncio.run(assess_verification(claim, retrieval))
        validate_verification_provenance(result.verification, plan, {source.evidence_id: source for source in retrieval.evidence})
        row.update(
            status="completed", observed=outcome_category(result.assessment_outcome),
            assessment_outcome=result.assessment_outcome, explanation=result.explanation,
            findings=[finding.model_dump(mode="json") for finding in result.verification.findings],
        )
    except Exception as error:
        # Avoid dumping request bodies, headers or credentials in an evaluation
        # report. The error class/code distinguish provider/contract failures.
        row.update(status="error", error_type=type(error).__name__, error_code=getattr(error, "error_code", None))
    row["elapsed_seconds"] = round(time.perf_counter() - started, 2)
    if 'retrieval' in locals():
        row['diagnostics'] = retrieval.trace.model_dump(mode='json')
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Opt in to existing Ollama planner/assessor calls (uses configured credentials and quota).")
    parser.add_argument("--pack", type=Path, default=PACK, help="Use a specified evidence regression pack instead of oracle_cases.json.")
    parser.add_argument("--case", action="append", dest="case_ids", help="Run only this case ID; repeat to select several.")
    parser.add_argument("--output", type=Path, help="JSON report path; live default is evaluation/verification/reports/<timestamp>.json.")
    args = parser.parse_args(argv)
    pack = load_cases(args.pack)
    selected = [case for case in pack["cases"] if not args.case_ids or case["id"] in args.case_ids]
    unknown = set(args.case_ids or []) - {case["id"] for case in pack["cases"]}
    if unknown:
        parser.error("Unknown case ID(s): " + ", ".join(sorted(unknown)))
    sys.path.insert(0, str(REPO / "backend"))
    as_of = datetime.fromisoformat(pack["as_of"])
    if not args.live:
        for case in selected:
            make_inputs(case, as_of)
        report = {"mode": "validation_only", "notice": pack["notice"], "validated_cases": len(selected),
                  "case_ids": [case["id"] for case in selected], "network_calls": 0}
        print(json.dumps(report, indent=2))
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return 0
    results = []
    for case in selected:
        row = run_case(case, as_of)
        results.append(row)
        print(f"{case['id']} expected={case['expected']} observed={row.get('observed', 'ERROR')} seconds={row['elapsed_seconds']}", flush=True)
    report = {"mode": "live_oracle", "version": pack["version"], "notice": pack["notice"],
              "assessment_as_of": pack["as_of"], "run_at": datetime.now().astimezone().isoformat(),
              "metrics": summarise(results), "results": results}
    output = args.output or HERE / "reports" / (datetime.now().strftime("oracle_%Y%m%d_%H%M%S") + ".json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["metrics"], indent=2))
    print(f"Report: {output}")
    return 1 if report["metrics"]["provider_or_contract_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
