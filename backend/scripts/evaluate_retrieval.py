"""Paired live retrieval + assessment evaluation; no Firestore writes or app quota.

Runs real input preparation and claim analysis once per case, then shares that
claim between modes. Reference URLs and expected labels NEVER enter the pipeline.
Provisional label agreement is diagnostic, not established real-world accuracy.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pipeline.claim_analysis.service import analyse_claim
from app.pipeline.evidence_assessment.semantic import configured_assessor
from app.pipeline.evidence_retrieval.service import retrieve_evidence, RETRIEVAL_VERSION
from app.pipeline.evidence_retrieval.enhanced import VERSION
from app.pipeline.input_preparation.service import prepare_text
from app.pipeline.orchestration.repository import InMemoryResultRepository
from app.pipeline.orchestration.service import PipelineOrchestrator
from app.pipeline.shared.errors import PipelineError

ROOT = Path(__file__).resolve().parents[2]
OUTCOMES = {"Low Concern": "supported", "High Concern": "refuted",
            "Needs Caution": "conflicting", "Not Enough Information": "insufficient"}


def run_case(case, modes, assessor, assessment_version, pause_seconds=0):
    if pause_seconds:
        time.sleep(pause_seconds)
    started = time.perf_counter()
    try:
        prepared = prepare_text(case["claim"])
        claim = analyse_claim(prepared)
    except Exception as error:
        return {"id": case["id"], "expected_provisional": case["expected"],
            "runs": {mode: {"error_code": getattr(error, "error_code", type(error).__name__)} for mode in modes}}
    shared_seconds = time.perf_counter() - started
    results = {}
    for mode in modes:
        if pause_seconds:
            time.sleep(pause_seconds)
        retrievals = []
        def retrieve(value):
            result = retrieve_evidence(value, mode=mode)
            retrievals.append(result.model_dump(mode="json"))
            return result
        pipeline = PipelineOrchestrator(prepare_input=lambda _: prepared,
            analyze_claim=lambda _: claim, retrieve_evidence=retrieve, assess_evidence=assessor,
            repository=InMemoryResultRepository(),
            pipeline_version=assessment_version + ":" + (VERSION if mode == "web" else RETRIEVAL_VERSION))
        started = time.perf_counter()
        try:
            result = pipeline.analyze(case["claim"])
            outcome = OUTCOMES[result.concern_label]
            results[mode] = {"outcome": outcome, "matches_provisional_label": outcome == case["expected"],
                "wrong_decisive": outcome in {"supported", "refuted"} and outcome != case["expected"],
                "quote_integrity": all(not item.evidence_quote or item.evidence_quote in item.passage for item in result.evidence),
                "result": result.model_dump(mode="json")}
        except PipelineError as error:
            results[mode] = {"error_code": error.error_code, "stage": error.stage}
        except Exception as error:
            # Never write raw exceptions/provider URLs that may carry secrets.
            results[mode] = {"error_code": type(error).__name__}
        results[mode]["duration_seconds"] = round(time.perf_counter() - started + shared_seconds, 2)
        results[mode]["retrieval"] = retrievals
    return {"id": case["id"], "input": case["claim"], "split": case["split"],
        "expected_provisional": case["expected"], "claim_analysis": claim.model_dump(mode="json"), "runs": results}


def summarise(cases, modes):
    summaries = {}
    for mode in modes:
        runs = [case["runs"][mode] for case in cases]
        durations = [run["duration_seconds"] for run in runs if "duration_seconds" in run]
        summaries[mode] = {"cases": len(runs),
            "provisional_label_matches": sum(run.get("matches_provisional_label", False) for run in runs),
            "wrong_decisive": sum(run.get("wrong_decisive", False) for run in runs),
            "errors": sum("error_code" in run for run in runs),
            "with_evidence": sum(bool(run.get("result", {}).get("evidence")) for run in runs),
            "insufficient": sum(run.get("outcome") == "insufficient" for run in runs),
            "quote_integrity_failures": sum(run.get("quote_integrity") is False for run in runs),
            "mean_seconds": round(statistics.mean(durations), 2) if durations else None,
            "max_seconds": max(durations) if durations else None}
    return summaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "evaluation/datasets/retrieval_seed_v1.json")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--split", choices=["development", "holdout", "regression", "all"], default="development")
    parser.add_argument("--mode", choices=["both", "catalogue", "web"], default="both")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, choices=[1, 2], default=1)
    parser.add_argument("--pause-seconds", type=float, default=5,
                        help="Cooldown before each case/mode; default 5 seconds to limit provider bursts.")
    parser.add_argument("--case-ids", nargs="+", help="Optional explicit subset within the selected split.")
    args = parser.parse_args()
    if args.report.exists():
        parser.error("Report already exists; choose a new path to preserve earlier results.")
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    cases = [case for case in dataset["cases"] if args.split == "all" or case["split"] == args.split]
    if args.case_ids:
        cases = [case for case in cases if case["id"] in args.case_ids]
        if set(args.case_ids) != {case["id"] for case in cases}:
            parser.error("Requested case IDs are not all present in this split.")
    if not 0 <= args.pause_seconds <= 60:
        parser.error("pause-seconds must be between 0 and 60.")
    if args.limit:
        cases = cases[:args.limit]
    modes = ["catalogue", "web"] if args.mode == "both" else [args.mode]
    assessor, version = configured_assessor()
    files = list((ROOT / "backend/app/pipeline").rglob("*.py"))
    report = {"run_at_utc": datetime.now(timezone.utc).isoformat(), "dataset": dataset["dataset_id"],
        "dataset_sha256": sha256(args.dataset.read_bytes()).hexdigest(),
        "code_sha256": {str(path.relative_to(ROOT)): sha256(path.read_bytes()).hexdigest() for path in sorted(files)},
        "scope": "Live input/claim/retrieval/assessment with in-memory result assembly. Pending human label/citation review. No Firestore writes or Android test. Shared claim analysis between modes, alternating mode order. Domain diversity is limited; not an independent benchmark.",
        "planned_cases": len(cases), "workers": args.workers, "pause_seconds": args.pause_seconds, "cases": []}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(run_case, case, modes if index % 2 == 0 else list(reversed(modes)), assessor, version, args.pause_seconds)
                   for index, case in enumerate(cases)]
        for future in as_completed(futures):
            result = future.result()
            report["cases"].append(result)
            report["summary"] = summarise(report["cases"], modes)
            args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(result["id"] + ": " + ", ".join(mode + "=" + run.get("outcome", run.get("error_code", "error"))
                  for mode, run in result["runs"].items()), flush=True)
    print(json.dumps(report["summary"], indent=2), flush=True)
    return 0 if all(value["errors"] == 0 for value in report["summary"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
