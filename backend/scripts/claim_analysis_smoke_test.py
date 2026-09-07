"""Opt-in live Ollama smoke test. Sends synthetic samples; consumes cloud usage.

Run from backend: python -m scripts.claim_analysis_smoke_test --report PATH
This checks claim analysis only, not retrieval, factual truth or Firestore.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from app.pipeline.claim_analysis.categories import CLASSIFICATION_MODELS, EXTRACTION_MODEL
from app.pipeline.claim_analysis.service import analyse_claim
from app.pipeline.shared.errors import PipelineError
from app.pipeline.shared.models import PreparedText


PROJECT = Path(__file__).resolve().parents[2]


def normalise(value):
    return " ".join(value.split()).casefold().rstrip(".!?") if value else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    dataset = PROJECT / "sprint_1_samples/02_matthew_claim_samples.json"
    samples = json.loads(dataset.read_text(encoding="utf-8"))["samples"]
    report = {
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Live claim-analysis smoke test on eight synthetic team samples; not an independent accuracy benchmark or an end-to-end fact check.",
        "dataset": str(dataset.relative_to(PROJECT)),
        "classification_models": CLASSIFICATION_MODELS,
        "extraction_model": EXTRACTION_MODEL,
        "confidence_meaning": "Winning classifier votes / 3, not probability of correctness.",
        "cases": [],
    }
    for sample in samples:
        started = time.perf_counter()
        expected = sample["expected_output"]
        case = {"scenario_id": sample["scenario_id"], "input": sample["input"]["normalised_text"],
                "expected": {key: expected[key] for key in ("claim_category", "checkable", "extracted_claim")}}
        try:
            result = analyse_claim(PreparedText.model_validate(sample["input"]))
            case["actual"] = result.model_dump()
            case["passed"] = (
                result.claim_category == expected["claim_category"]
                and result.checkable == expected["checkable"]
                and normalise(result.extracted_claim) == normalise(expected["extracted_claim"])
            )
        except PipelineError as error:
            case["error"] = {"error_code": error.error_code, "stage": error.stage}
            case["passed"] = False
        case["duration_seconds"] = round(time.perf_counter() - started, 2)
        report["cases"].append(case)
        print(f"{case['scenario_id']}: {'PASS' if case['passed'] else 'FAIL'} ({case['duration_seconds']}s)", flush=True)
    report["passed"] = sum(case["passed"] for case in report["cases"])
    report["total"] = len(samples)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Saved report: {report['passed']}/{report['total']} passed", flush=True)
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
