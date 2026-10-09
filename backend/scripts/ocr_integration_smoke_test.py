"""Run live OCR, fact-checking and Firestore with an isolated test identity.

No real user's allowance is touched. All temporary Firestore records are removed.
Authentication is overridden: this tests integration, not Firebase sign-in.
The OCR model and existing fact-check providers must be running/configured.
"""

import argparse
import base64
import io
import json
from pathlib import Path
import time
from uuid import uuid4

from fastapi.testclient import TestClient
from google.cloud.firestore_v1.base_query import FieldFilter
from PIL import Image, ImageDraw, ImageFont

from app.analyses.store import FirestoreAnalysisStore, get_analysis_store
from app.auth.dependencies import get_current_user
from app.auth.models import AuthenticatedUser
from app.firebase import get_firestore_client
from app.main import app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--image", type=Path)
    args = parser.parse_args()
    image = Image.new("RGB", (1300, 350), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 40)
    draw.text((45, 50), "Singapore became independent", font=font, fill="black")
    draw.text((45, 135), "on 9 August 1965.", font=font, fill="black")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    if args.image:
        args.image.parent.mkdir(parents=True, exist_ok=True)
        args.image.write_bytes(buffer.getvalue())
    uid = "uiabo-integration-ocr-" + uuid4().hex
    client = get_firestore_client()
    store = FirestoreAnalysisStore(client)
    previous = dict(app.dependency_overrides)
    report = {"authentication": "isolated identity override", "ocr": "live",
              "fact_check": "live", "firestore": "live"}
    try:
        client.collection("users").document(uid).set({"uid": uid, "role": "premium", "account_status": "active"})
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(uid=uid, email="ocr-test@example.com", email_verified=True)
        app.dependency_overrides[get_analysis_store] = lambda: store
        with TestClient(app) as api:
            started = time.perf_counter()
            response = api.post("/analysis/ocr", json={"image_base64": base64.b64encode(buffer.getvalue()).decode()})
            if response.status_code != 200:
                raise RuntimeError(response.json().get("detail", {}).get("error_code", "OCR_FAILED"))
            preview = response.json()
            assert "9 August 1965" in preview["text"]
            report["ocr_seconds"] = round(time.perf_counter() - started, 2)
            report["extracted_text"] = preview["text"]
            assert not client.collection("usage_allowances").document(uid).get().exists
            assert api.get("/analysis/results").json()["results"] == []
            print("Live OCR extracted the sample; no allowance or history record created.", flush=True)
            started = time.perf_counter()
            payload = {"text": preview["text"], "input_source": "ocr"}
            headers = {"Idempotency-Key": "ocr-fact-check"}
            response = api.post("/analysis/text", json=payload, headers=headers)
            if response.status_code != 200:
                raise RuntimeError(response.json().get("detail", {}).get("error_code", "FACT_CHECK_FAILED"))
            result = response.json()
            assert result["input_source"] == "ocr"
            assert api.post("/analysis/text", json=payload, headers=headers).json() == result
            detail = api.get("/analysis/results/" + result["result_id"]).json()
            assert detail["input_source"] == "ocr" and detail["original_text"] == preview["text"]
            allowance = client.collection("usage_allowances").document(uid).get().to_dict()
            assert allowance["remaining_submissions"] == 59 and allowance["successful_submissions"] == 1
            report["fact_check_seconds"] = round(time.perf_counter() - started, 2)
            report["assessment_outcome"] = result.get("assessment_outcome")
            report["concern_label"] = result["concern_label"]
            report["evidence_count"] = len(result["evidence"])
            report["checks"] = {"ocr_free_of_charge": True, "image_not_saved": True,
                                "reviewed_text_saved": True, "source_preserved": True,
                                "idempotent_replay": True, "fact_check_charged_once": True}
            print("Fact-check completed and saved; replay used no additional allowance.", flush=True)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        for snapshot in client.collection("analysis_results").where(filter=FieldFilter("user_id", "==", uid)).stream():
            snapshot.reference.delete()
        for collection in ("users", "usage_allowances", "analysis_locks"):
            client.collection(collection).document(uid).delete()
    report["temporary_documents_removed"] = True
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("OCR integration smoke test passed; temporary documents removed.", flush=True)


if __name__ == "__main__":
    main()
