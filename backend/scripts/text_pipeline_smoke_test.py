"""Opt-in live text pipeline test; uses Ollama, Google and Tavily allowance.

Run from backend: python -m scripts.text_pipeline_smoke_test --report PATH
Uses FastAPI TestClient and an in-memory repository, never live Firestore.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from fastapi.testclient import TestClient

from app.main import app
from app.pipeline.claim_analysis.service import analyse_claim
from app.pipeline.evidence_assessment.semantic import configured_assessor
from app.pipeline.evidence_retrieval.service import configured_retriever
from app.pipeline.input_preparation.service import prepare_text
from app.pipeline.orchestration.dependencies import get_pipeline_orchestrator
from app.pipeline.orchestration.repository import InMemoryResultRepository
from app.pipeline.orchestration.service import PipelineOrchestrator
from app.analyses.store import InMemoryAnalysisStore, get_analysis_store
from app.auth.dependencies import get_current_user
from app.auth.models import AuthenticatedUser


CASES = [
    ("published_fact_check", "The Great Wall of China is visible from the Moon.", True),
    ("government_history", "Singapore became independent on 9 August 1965.", True),
    ("opinion", "Chicken rice is the best food in Singapore.", False),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    repository = InMemoryResultRepository()
    assessor, version = configured_assessor()
    retriever, retrieval_version = configured_retriever()
    retrievals = []
    def capture_retrieval(claim):
        result = retriever(claim)
        retrievals.append(result.model_dump(mode="json"))
        return result
    pipeline = PipelineOrchestrator(
        prepare_input=prepare_text, analyze_claim=analyse_claim,
        retrieve_evidence=capture_retrieval, assess_evidence=assessor,
        repository=repository, pipeline_version=version + ":" + retrieval_version)
    report = {
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Live text stages through FastAPI TestClient; in-memory persistence. Operational checks only, not an accuracy benchmark or Android test.",
        "cases": [],
    }
    previous = app.dependency_overrides.get(get_pipeline_orchestrator)
    previous_overrides = dict(app.dependency_overrides)
    store = InMemoryAnalysisStore()
    identity = {"uid": "smoke-initial"}
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        uid=identity["uid"], email="smoke@example.invalid", email_verified=True)
    app.dependency_overrides[get_analysis_store] = lambda: store
    app.dependency_overrides[get_pipeline_orchestrator] = lambda: pipeline
    try:
        with TestClient(app) as client:
            for name, text, checkable in CASES:
                identity["uid"] = "smoke-" + name
                store.documents["users", identity["uid"]] = {
                    "uid": identity["uid"], "role": "free", "account_status": "active"}
                retrievals.clear()
                started = time.perf_counter()
                response = client.post("/analysis/text", json={"text": text})
                body = response.json()
                passed = (response.status_code == 200 and body.get("checkable") == checkable
                          and (bool(body.get("evidence")) if checkable else not retrievals))
                case = {"scenario_id": name, "input": text, "http_status": response.status_code,
                        "operational_check_passed": passed,
                        "duration_seconds": round(time.perf_counter() - started, 2),
                        "response": body, "retrieval": list(retrievals)}
                report["cases"].append(case)
                print(f"{name}: HTTP {response.status_code}, {body.get('concern_label', 'error')}, {len(body.get('evidence', []))} sources ({case['duration_seconds']}s)", flush=True)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
    records = [data for (collection, _), data in store.documents.items() if collection == "analysis_results"]
    report["saved_completed"] = sum(data["processing_status"] == "completed" for data in records)
    report["saved_failed"] = sum(data["processing_status"] == "failed" for data in records)
    report["operational_checks_passed"] = sum(case["operational_check_passed"] for case in report["cases"])
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"Report saved; {report['operational_checks_passed']}/{len(CASES)} operational checks passed.")
    return 0 if report["operational_checks_passed"] == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
