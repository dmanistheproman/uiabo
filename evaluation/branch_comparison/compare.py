"""Compare two working trees without starting the app or writing to Firebase.

Standard-library coordinator. Each case/branch uses that tree's own Python in
a fresh subprocess. Run --help. No network requests without --execute.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
LABELS = {"supported", "contradicted", "unresolved", "not_checkable", "forecast_conflict"}
FORECAST_URL = "https://api-open.data.gov.sg/v2/real-time/api/four-day-outlook"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_cases(path, split):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    all_cases = data["cases"]
    if len({c["id"] for c in all_cases}) != len(all_cases):
        raise ValueError("Duplicate case IDs")
    if len({c["claim"].strip().casefold() for c in all_cases}) != len(all_cases):
        raise ValueError("Duplicate claims")
    groups = {}
    for c in all_cases:
        if c["split"] not in {"pilot", "final", "regression"} or not c["claim"].strip():
            raise ValueError("Invalid case")
        groups.setdefault(c["group"], set()).add(c["split"])
    if any(len(splits) > 1 for splits in groups.values()):
        raise ValueError("A scenario group crosses splits")
    cases = [c for c in all_cases if c["split"] == split]
    if not cases:
        raise ValueError("Empty split")
    return cases


def load_labels(path, cases, dataset_hash):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate label IDs")
    rows = {r["id"]: r for r in rows}
    selected = {}
    for case in cases:
        row = rows.get(case["id"], {})
        required = ("reviewer_a", "label_a", "reason_a", "reviewer_b", "label_b", "reason_b",
                    "final_label", "adjudicator", "decision_reason", "reviewed_at", "dataset_sha256")
        if any(not row.get(key, "").strip() for key in required):
            raise ValueError(f"{case['id']}: independent review/adjudication is incomplete")
        if row["reviewer_a"].strip().casefold() == row["reviewer_b"].strip().casefold():
            raise ValueError(f"{case['id']}: two distinct reviewers required")
        if any(row[k] not in LABELS for k in ("label_a", "label_b", "final_label")):
            raise ValueError(f"{case['id']}: invalid label")
        if row["dataset_sha256"] != dataset_hash:
            raise ValueError("Labels refer to a different dataset version")
        for suffix in ("a", "b"):
            if row[f"label_{suffix}"] != "not_checkable" and not row.get(f"sources_{suffix}", "").strip():
                raise ValueError(f"{case['id']}: reviewer {suffix} needs evidence or a search record")
        if row["final_label"] != "not_checkable" and not row.get("final_sources", "").strip():
            raise ValueError(f"{case['id']}: final evidence/search record is missing")
        datetime.fromisoformat(row["reviewed_at"])
        selected[case["id"]] = row
    return selected


def fingerprint(root):
    root = Path(root).resolve()
    python = root / "backend/.venv/Scripts/python.exe"
    if not python.exists():
        python = root / "backend/.venv/bin/python"
    if not python.exists():
        raise ValueError(f"Missing backend virtual environment: {root}")
    files = [p for p in (root / "backend/app/pipeline").rglob("*")
             if p.is_file() and p.suffix in {".py", ".json", ".txt", ".yaml", ".yml"}]
    files += [p for p in (root / "backend").glob("*requirements*.txt")]
    if not files:
        raise ValueError("Missing pipeline source files")
    hashes = {p.relative_to(root).as_posix(): digest(p) for p in sorted(files)}
    def git(*args):
        proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
        return proc.stdout.strip() if proc.returncode == 0 else "unavailable"
    return {"root": str(root), "python": str(python), "head": git("rev-parse", "HEAD"),
            "branch": git("branch", "--show-current"),
            "source_sha256": hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
            "files": hashes}


def outcome(result):
    value = result.get("assessment_outcome")
    if value == "contradicted" and (result.get("forecast_context") or {}).get("risk_basis") == "forecast_comparison":
        return "forecast_conflict"
    if result.get("checkable") is False or value == "not_checkable":
        return "not_checkable"
    if value in {"supported", "contradicted"}:
        return value
    # Never turn a 50 risk score or a provider failure into a factual verdict.
    # Historical plausibility is not a verified falsehood. Existing truth-label
    # benchmarks keep it unresolved; inspect plausibility_context separately.
    if value in {"unsupported", "conflicting", "insufficient_evidence", "highly_unlikely"}:
        return "unresolved"
    raise ValueError("Unsupported result contract: missing assessment_outcome")


def summarise(cases, labels):
    summary = {}
    for branch in ("original", "experimental"):
        runs = [(c, c["runs"][branch]) for c in cases if branch in c["runs"]]
        checked = [(c, r) for c, r in runs if c["id"] in labels]
        correct = sum(r.get("outcome") == labels[c["id"]]["final_label"] for c, r in checked)
        decisive = [(c, r) for c, r in checked if r.get("outcome") in {"supported", "contradicted", "forecast_conflict"}]
        unsafe = sum(r["outcome"] != labels[c["id"]]["final_label"] for c, r in decisive)
        durations = [r["duration_seconds"] for _, r in runs]
        confusion = {}
        for c, r in checked:
            expected = labels[c["id"]]["final_label"]
            predicted = r.get("outcome", "error")
            confusion.setdefault(expected, {})[predicted] = confusion.get(expected, {}).get(predicted, 0) + 1
        summary[branch] = {"attempted": len(runs), "labelled": len(checked), "correct": correct,
            "accuracy_including_errors": correct / len(checked) if checked else None,
            "errors": sum("error_code" in r for _, r in runs),
            "unresolved": sum(r.get("outcome") == "unresolved" for _, r in runs),
            "wrong_decisive": unsafe,
            "decisive_precision": (len(decisive) - unsafe) / len(decisive) if decisive else None,
            "decisive_coverage": sum(r.get("outcome") in {"supported", "contradicted", "forecast_conflict"} for _, r in runs) / len(runs) if runs else None,
            "median_seconds": statistics.median(durations) if durations else None,
            "p95_seconds": sorted(durations)[max(0, int(len(durations) * .95 + .999999) - 1)] if durations else None,
            "http_attempts": sum(len(r.get("requests", [])) for _, r in runs),
            "confusion": confusion}
        per_class = {}
        for label in sorted({labels[c['id']]['final_label'] for c, _ in checked} | {r['outcome'] for _, r in checked if 'outcome' in r}):
            tp = confusion.get(label, {}).get(label, 0)
            actual = sum(confusion.get(label, {}).values())
            predicted = sum(row.get(label, 0) for row in confusion.values())
            per_class[label] = {"support": actual, "predicted": predicted,
                "precision": tp / predicted if predicted else 0,
                "recall": tp / actual if actual else 0,
                "f1": 2 * tp / (actual + predicted) if actual + predicted else 0}
        summary[branch]["per_class"] = per_class
        summary[branch]["macro_f1"] = statistics.mean(v['f1'] for v in per_class.values()) if per_class else None
        groups = {}
        topics = {}
        for c, r in checked:
            match = r.get('outcome') == labels[c['id']]['final_label']
            groups.setdefault(c['group'], []).append(match)
            topics.setdefault(c['topic'], []).append(match)
        summary[branch]['mean_group_accuracy'] = statistics.mean(statistics.mean(v) for v in groups.values()) if groups else None
        summary[branch]['topic_accuracy'] = {k: {'correct': sum(v), 'cases': len(v), 'accuracy': sum(v)/len(v)} for k,v in topics.items()}
    paired = [c for c in cases if len(c["runs"]) == 2 and c["id"] in labels]
    summary["paired"] = {"cases": len(paired), "experimental_only_correct": 0, "original_only_correct": 0}
    for c in paired:
        correct = {b: c["runs"][b].get("outcome") == labels[c["id"]]["final_label"] for b in c["runs"]}
        if correct["experimental"] and not correct["original"]:
            summary["paired"]["experimental_only_correct"] += 1
        if correct["original"] and not correct["experimental"]:
            summary["paired"]["original_only_correct"] += 1
    return summary


def worker_payload(case, assessed_at, fixture):
    # Reviewer metadata and gold labels must never enter model prompts/processes.
    return {"claim": case["claim"], "assessed_at": assessed_at, "forecast_fixture": fixture}


def run_worker(tree, branch, payload, credentials, timeout):
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("PYTHONPATH", None)
    env.pop("PYTHON_DOTENV_DISABLED", None)
    started = time.perf_counter()
    try:
        proc = subprocess.run([tree["python"], "-B", str(HERE / "worker.py"),
            "--backend", str(Path(tree["root"]) / "backend"), "--branch", branch,
            "--credentials", str(credentials)], input=json.dumps(payload),
            text=True, encoding="utf-8", capture_output=True, cwd=Path(tree["root"]) / "backend",
            env=env, timeout=timeout)
        if proc.returncode != 0:
            result = {"error_code": "WORKER_FAILED", "worker_exit_code": proc.returncode}
        else:
            result = json.loads(proc.stdout)
    except subprocess.TimeoutExpired:
        result = {"error_code": "WORKER_TIMEOUT"}
    except (ValueError, OSError):
        result = {"error_code": "WORKER_PROTOCOL_ERROR"}
    result["duration_seconds"] = round(time.perf_counter() - started, 3)
    return result


def save_report(path, report):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--split", choices=["pilot", "final", "regression"], default="pilot")
    parser.add_argument("--original", type=Path, default=Path("C:/Dev/uiabo"))
    parser.add_argument("--experimental", type=Path, default=HERE.parents[1])
    parser.add_argument("--credentials", type=Path, help="Shared credential file; defaults to experimental repository root .env")
    parser.add_argument("--labels", type=Path, help="Completed adjudication CSV; required for final execution")
    parser.add_argument("--report", type=Path, help="New JSON report path; existing reports are never overwritten")
    parser.add_argument("--forecast-fixture", type=Path)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--pause", type=float, default=5)
    parser.add_argument("--limit", type=int, help="Pilot/regression only")
    parser.add_argument("--execute", action="store_true", help="Spend API usage on live full-pipeline runs")
    args = parser.parse_args(argv)
    args.dataset = args.dataset or HERE / "datasets" / f"{args.split}.json"
    try:
        cases = load_cases(args.dataset, args.split)
        if args.limit is not None:
            if args.split == "final" or args.limit < 1:
                raise ValueError("Only pilot/regression allow a positive --limit")
            cases = cases[:args.limit]
        if not 0 <= args.pause <= 60 or not 30 <= args.timeout <= 900:
            raise ValueError("Use pause 0..60 and timeout 30..900")
        dataset_hash = digest(args.dataset)
        labels = load_labels(args.labels, cases, dataset_hash) if args.labels else {}
        trees = {"original": fingerprint(args.original), "experimental": fingerprint(args.experimental)}
        if args.original.resolve() == args.experimental.resolve():
            raise ValueError("Select two different working trees")
        fixture = json.loads(args.forecast_fixture.read_text(encoding="utf-8")) if args.forecast_fixture else None
        if fixture and fixture.get("url") != FORECAST_URL:
            raise ValueError("Unexpected forecast fixture source")
        assessed_at = fixture["assessed_at"] if fixture else datetime.now(timezone.utc).isoformat()
        if datetime.fromisoformat(assessed_at).utcoffset() is None:
            raise ValueError("Clock needs a timezone")
        if not args.execute:
            print(json.dumps({"mode": "dry_run_no_api_calls", "split": args.split,
                "cases": len(cases), "groups": len({c['group'] for c in cases}), "dataset_sha256": dataset_hash,
                "reviewed_cases": len(labels), "planned_pipeline_runs": 2 * len(cases),
                "trees": {b: {k: v for k, v in t.items() if k not in {'files', 'python'}} for b, t in trees.items()}}, indent=2))
            return 0
        if args.split == "final" and not labels:
            raise ValueError("Final test requires completed independent labels via --labels")
        if any(c.get("requires_forecast") for c in cases) and not fixture:
            raise ValueError("Weather regression needs one shared snapshot. Run snapshot_weather.py first")
        if not args.report or args.report.exists():
            raise ValueError("Supply a new --report path")
        credentials = (args.credentials or args.experimental / ".env").resolve()
        if not credentials.is_file():
            raise ValueError("Shared credentials file is missing")
        preflight = {branch: run_worker(tree, branch, {"preflight": True, "assessed_at": assessed_at}, credentials, 30)
                     for branch, tree in trees.items()}
        if any(not value.get("ready") for value in preflight.values()):
            raise ValueError("Offline pipeline preflight failed. Check both virtual environments and shared OLLAMA_API_KEY, TAVILY_API_KEY and JEV_API_KEY settings")
        report = {"schema": 1, "split": args.split, "started_at": datetime.now(timezone.utc).isoformat(),
            "assessed_at": assessed_at, "dataset_sha256": dataset_hash,
            "labels_sha256": digest(args.labels) if args.labels else None, "trees": trees,
            "runner_sha256": {p.name: digest(p) for p in (HERE / 'compare.py', HERE / 'worker.py')},
            "forecast_fixture_sha256": digest(args.forecast_fixture) if fixture else None,
            "planned_cases": len(cases), "planned_groups": len({c['group'] for c in cases}),
            "preflight": preflight, "status": "running", "cases": [], "scope": "Full pipelines; shared credentials/config profile; live search; in-memory persistence; no app checks. HTTP attempts are not billable credits."}
        args.report.parent.mkdir(parents=True, exist_ok=True)
        # Reserve output exclusively before the first live request.
        with args.report.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
        for index, case in enumerate(cases):
            item = {"id": case["id"], "claim": case["claim"], "group": case["group"], "topic": case["topic"], "runs": {}}
            report["cases"].append(item)
            order = ["original", "experimental"] if index % 2 == 0 else ["experimental", "original"]
            item["order"] = order
            for branch in order:
                if fingerprint(trees[branch]["root"])["source_sha256"] != trees[branch]["source_sha256"]:
                    report["status"] = "stopped_code_changed"
                    save_report(args.report, report)
                    raise ValueError("Pipeline source changed during comparison; preserve report and start a new run")
                item["runs"][branch] = run_worker(trees[branch], branch,
                    worker_payload(case, assessed_at, fixture), credentials, args.timeout)
                report["summary"] = summarise(report["cases"], labels)
                save_report(args.report, report)
                print(f"{case['id']} {branch}: {item['runs'][branch].get('outcome', item['runs'][branch].get('error_code'))}", flush=True)
                if args.pause:
                    time.sleep(args.pause)
        report["status"] = "complete"
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        report["code_unchanged_at_end"] = all(fingerprint(t["root"])["source_sha256"] == t["source_sha256"] for t in trees.values())
        save_report(args.report, report)
        print(json.dumps(report["summary"], indent=2))
        return 0
    except (ValueError, KeyError, OSError) as error:
        # These are local configuration errors. Worker/provider messages never enter this path.
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
