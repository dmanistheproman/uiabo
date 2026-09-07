"""Opt-in real auth/API/Firestore check using two dedicated test accounts.

Run from backend: python -m scripts.firestore_app_smoke_test --help

Pass --login-file pointing OUTSIDE Git to JSON with api/android entries containing
uid, email and password. Accounts must be verified and have uid prefix
'uiabo-integration-'. This script writes a real result and uses one test allowance.
"""

import argparse
import json
from pathlib import Path
import time

from dotenv import dotenv_values
import httpx

from app.firebase import get_firestore_client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--login-file", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[2]
    web_key = dotenv_values(project / "mobile/.env")["EXPO_PUBLIC_FIREBASE_API_KEY"]
    logins = json.loads(args.login_file.read_text())
    assert all(item["uid"].startswith("uiabo-integration-") for item in logins.values())
    headers = {}
    with httpx.Client(timeout=180) as client:
        for name, login in logins.items():
            response = client.post("https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword",
                params={"key": web_key}, json={"email": login["email"], "password": login["password"], "returnSecureToken": True})
            assert response.status_code == 200, "Test account sign-in failed"
            headers[name] = {"Authorization": "Bearer " + response.json()["idToken"]}
            response = client.put(args.api_url + "/account/me", headers=headers[name], json={"name": "Alex Tester"})
            assert response.status_code == 200, "Profile setup failed"
        started = time.perf_counter()
        request_headers = {**headers["api"], "Idempotency-Key": "firestore-live-first"}
        payload = {"text": "Singapore became independent on 9 August 1965."}
        response = client.post(args.api_url + "/analysis/text", headers=request_headers, json=payload)
        assert response.status_code == 200, f"Live analysis HTTP {response.status_code}"
        result = response.json()
        second = client.post(args.api_url + "/analysis/text", headers=request_headers, json=payload)
        history = client.get(args.api_url + "/analysis/results", headers=headers["api"])
        detail_url = args.api_url + "/analysis/results/" + result["result_id"]
        detail = client.get(detail_url, headers=headers["api"])
        forbidden = client.get(detail_url, headers=headers["android"])
        depleted = client.post(args.api_url + "/analysis/text", headers={**headers["api"], "Idempotency-Key": "firestore-live-second"}, json=payload)
        profile = client.get(args.api_url + "/account/me", headers=headers["api"])
        assert second.status_code == 200 and second.json()["result_id"] == result["result_id"]
        assert history.status_code == detail.status_code == 200
        assert forbidden.status_code == 404 and depleted.status_code == 429
        assert profile.json()["allowance"]["remaining_submissions"] == 0
        stored = get_firestore_client().collection("analysis_results").document(result["result_id"]).get().to_dict()
        assert stored["user_id"] == logins["api"]["uid"]
        assert stored["evidence"] == result["evidence"]
        report = {"scope": "Real Firebase ID tokens, live API/pipeline, real Firestore using isolated test accounts.",
            "duration_seconds": round(time.perf_counter() - started, 2), "result": result,
            "checks": {"idempotent_retry_same_result": True, "owner_history_read": True,
                "owner_detail_read": True, "other_user_rejected_404": True,
                "second_submission_rejected_429": True, "remaining_allowance_zero": True,
                "firestore_owner_and_evidence_verified": True}}
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
        print("Live Firestore ownership, history, idempotency and allowance checks passed.")


if __name__ == "__main__":
    main()
