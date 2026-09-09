"""Compare lexical and semantic stance on frozen passages. No retrieval/Firestore.

From backend: python -m scripts.evaluate_stance --mode compare --split development
              --report ../evaluation/reports/stance_development.json
Live comparison uses the existing Ollama key and allowance. Lexical mode is offline.
"""

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import statistics
import time

import httpx

from app.pipeline.evidence_assessment import semantic
from app.pipeline.evidence_assessment.service import classify_stance
from app.pipeline.shared.models import EvidenceCandidate

ROOT = Path(__file__).resolve().parents[2]
LABELS = ("supporting", "contradicting", "neutral")


def metrics(rows, field):
    matrix = {expected: {actual: 0 for actual in (*LABELS, "error")} for expected in LABELS}
    for row in rows:
        matrix[row["expected_stance"]][row.get(field) or "error"] += 1
    count = len(rows)
    correct = sum(matrix[label][label] for label in LABELS)
    per_label = {}
    for label in LABELS:
        tp = matrix[label][label]
        predicted = sum(matrix[other][label] for other in LABELS)
        expected = sum(matrix[label].values())
        precision = tp / predicted if predicted else 0
        recall = tp / expected if expected else 0
        per_label[label] = {"precision": round(precision, 4), "recall": round(recall, 4),
                            "f1": round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0}
    decisive = sum(matrix[label][prediction] for label in LABELS for prediction in LABELS[:2])
    false_support = matrix["contradicting"]["supporting"] + matrix["neutral"]["supporting"]
    nonsupport = sum(sum(matrix[label].values()) for label in LABELS[1:])
    return {"count": count, "correct": correct,
            "accuracy_including_errors": round(correct / count, 4) if count else None,
            "macro_f1": round(statistics.mean(v["f1"] for v in per_label.values()), 4),
            "per_label": per_label, "confusion_matrix": matrix,
            "technical_errors": sum(matrix[label]["error"] for label in LABELS),
            "false_support_count": false_support,
            "false_support_rate_among_non_supporting": round(false_support / nonsupport, 4) if nonsupport else None,
            "decision_coverage": round(decisive / count, 4) if count else None,
            "accuracy_when_decisive": round((matrix["supporting"]["supporting"] + matrix["contradicting"]["contradicting"]) / decisive, 4) if decisive else None}


def validate_dataset(data):
    ids, groups = set(), {}
    for case in data["cases"]:
        if case["id"] in ids:
            raise ValueError("Duplicate dataset ID")
        ids.add(case["id"])
        if case["expected_stance"] not in LABELS:
            raise ValueError("Invalid expected stance")
        if groups.setdefault(case["group"], case["split"]) != case["split"]:
            raise ValueError("Scenario group crosses evaluation splits")
        EvidenceCandidate.model_validate(case["evidence"])


async def compare(cases, model, concurrency):
    semaphore = asyncio.Semaphore(concurrency)
    rows = []
    async with httpx.AsyncClient(base_url="https://ollama.com",
                                headers={"Authorization": f"Bearer {semantic.api_key()}"},
                                timeout=httpx.Timeout(semantic.REQUEST_TIMEOUT_SECONDS, connect=10.0)) as client:
        async def run(case):
            async with semaphore:
                started = time.perf_counter()
                row = baseline_row(case)
                try:
                    verdict = await semantic.judge_with_client(client, case["claim"],
                        EvidenceCandidate.model_validate(case["evidence"]), model)
                    row.update(semantic_stance=verdict.stance, evidence_quote=verdict.evidence_quote,
                               semantic_reason=verdict.reason, error_code=None)
                except (httpx.HTTPError, TimeoutError, ValueError, TypeError, KeyError, AttributeError) as error:
                    # Never serialize raw provider errors, headers or credentials.
                    row.update(semantic_stance=None, error_code=type(error).__name__)
                row["duration_seconds"] = round(time.perf_counter() - started, 3)
                rows.append(row)
                if len(rows) % 10 == 0 or len(rows) == len(cases):
                    print(f"Completed {len(rows)}/{len(cases)}; provider/validation errors: {sum(r.get('error_code') is not None for r in rows)}", flush=True)
        await asyncio.gather(*(run(case) for case in cases))
    return sorted(rows, key=lambda row: row["id"])


def baseline_row(case):
    return {"id": case["id"], "group": case["group"], "split": case["split"],
            "kind": case["kind"], "review_status": case["review_status"],
            "expected_stance": case["expected_stance"],
            "baseline_stance": classify_stance(case["claim"], case["evidence"]["passage"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "evaluation/datasets/stance_seed_v1.json")
    parser.add_argument("--mode", choices=("lexical", "compare"), default="lexical")
    parser.add_argument("--split", choices=("all", "development", "holdout", "regression"), default="all")
    parser.add_argument("--model", default=semantic.DEFAULT_MODEL)
    parser.add_argument("--concurrency", type=int, choices=range(1, 4), default=3)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.dataset.read_text(encoding="utf-8"))
    validate_dataset(data)
    cases = [case for case in data["cases"] if args.split == "all" or case["split"] == args.split]
    rows = asyncio.run(compare(cases, args.model, args.concurrency)) if args.mode == "compare" else [baseline_row(case) for case in cases]
    summary = {}
    for split in sorted({row["split"] for row in rows}):
        selected = [row for row in rows if row["split"] == split]
        summary[split] = {"baseline": metrics(selected, "baseline_stance")}
        if args.mode == "compare":
            summary[split]["semantic"] = metrics(selected, "semantic_stance")
    durations = sorted(row["duration_seconds"] for row in rows if "duration_seconds" in row)
    report = {"run_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": data["scope"], "mode": args.mode, "model": args.model if args.mode == "compare" else None,
              "prompt_version": semantic.PROMPT_VERSION,
              "prompt_sha256": sha256((semantic.SYSTEM_PROMPT + "\n" + semantic.REPAIR_INSTRUCTION).encode()).hexdigest(),
              "semantic_code_sha256": sha256(Path(semantic.__file__).read_bytes()).hexdigest(),
              "dataset_sha256": sha256(args.dataset.read_bytes()).hexdigest(),
              "dataset_version": data["version"], "labels": "Provisional, authored by Codex; independent human review pending.",
              "split_policy": "Scenario groups kept together; holdout must not be used for prompt tuning.",
              "summary": summary, "latency_seconds": {
                  "mean": round(statistics.mean(durations), 3),
                  "p95": durations[min(len(durations) - 1, int(len(durations) * 0.95))],
              } if durations else None, "cases": rows}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for split, methods in summary.items():
        for name, result in methods.items():
            print(f"{split} {name}: {result['correct']}/{result['count']} correct; {result['false_support_count']} false supports; {result['technical_errors']} technical errors")
    return 1 if any(row.get("error_code") for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
