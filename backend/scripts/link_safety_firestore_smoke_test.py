"""Opt-in Firestore transaction smoke test using temporary documents.

Runs the real link route/store with an isolated identity dependency and mock Web
Risk responses by default. Pass --live-provider to call Google instead. This is
not a Firebase sign-in test. No existing user's allowance is modified. Temporary
profiles, locks, allowances and results are removed in the finally block.
"""

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
import httpx

from app.analyses.store import FirestoreAnalysisStore, get_analysis_store
from app.auth.dependencies import get_current_user
from app.auth.models import AuthenticatedUser
from app.firebase import get_firestore_client
from app.link_safety.service import WebRiskClient, get_web_risk_client
from app.main import app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-provider", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    client = get_firestore_client()
    store = FirestoreAnalysisStore(client)
    uid = "uiabo-integration-link-" + uuid4().hex
    identity = {"user": AuthenticatedUser(uid=uid, email="link-test@example.com", email_verified=True)}
    report = {"firestore": "live", "authentication": "isolated identity override",
              "web_risk": "live" if args.live_provider else "mock", "checks": {}}
    original_overrides = dict(app.dependency_overrides)
    records = []
    def respond(request):
        if request.url.params["uri"].endswith("/s/malware.html"):
            return httpx.Response(200, json={"threat": {"threatTypes": ["MALWARE"],
                "expireTime": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()}})
        return httpx.Response(200, json={})
    service = get_web_risk_client() if args.live_provider else WebRiskClient("mock", transport=httpx.MockTransport(respond))
    try:
        client.collection("users").document(uid).set({"uid": uid, "role": "premium", "account_status": "active"})
        app.dependency_overrides[get_analysis_store] = lambda: store
        app.dependency_overrides[get_current_user] = lambda: identity["user"]
        app.dependency_overrides[get_web_risk_client] = lambda: service
        with TestClient(app) as api:
            for name, url, expected in [
                ("malware_test", "http://testsafebrowsing.appspot.com/s/malware.html", "threat_detected"),
                ("no_match_test", "https://example.com/", "no_known_threats"),
            ]:
                headers = {"Idempotency-Key": name.replace("_", "-")}
                response = api.post("/analysis/link-safety", json={"url": url}, headers=headers)
                if response.status_code != 200:
                    raise RuntimeError(response.json().get("detail", {}).get("error_code", "LINK_CHECK_FAILED"))
                body = response.json()
                assert body["safety_status"] == expected
                result_id = body["result_id"]
                records.append(result_id)
                stored = client.collection("analysis_results").document(result_id).get().to_dict()
                assert stored["input_type"] == "link_safety" and stored["user_id"] == uid
                assert api.get(f"/analysis/results/{result_id}").json() == body
                assert api.post("/analysis/link-safety", json={"url": url}, headers=headers).json() == body
                report["checks"][name] = {"safety_status": body["safety_status"], "threat_types": body["threat_types"]}
            assert len(api.get("/analysis/results").json()["results"]) == 2
            allowance = client.collection("usage_allowances").document(uid).get().to_dict()
            assert allowance["successful_submissions"] == 2 and allowance["remaining_submissions"] == 58
            identity["user"] = identity["user"].model_copy(update={"uid": uid + "-other"})
            # A missing profile must also be unable to read the owner's result.
            assert api.get(f"/analysis/results/{records[0]}").status_code == 404
            report["checks"].update(history_and_detail=True, idempotent_replay=True,
                                    charged_once_per_result=True, other_identity_rejected=True)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)
        # Query catches failed records too; all documents belong to this unique test identity.
        from google.cloud.firestore_v1.base_query import FieldFilter
        for snapshot in client.collection("analysis_results").where(filter=FieldFilter("user_id", "==", uid)).stream():
            snapshot.reference.delete()
        for collection in ("analysis_locks", "usage_allowances", "users"):
            client.collection(collection).document(uid).delete()
    report["temporary_documents_removed"] = True
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Link route, real Firestore storage, history, replay and allowance smoke test passed; temporary documents removed.")


if __name__ == "__main__":
    main()
