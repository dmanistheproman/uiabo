import os

import pytest
from unittest.mock import patch
from google.genai.errors import ClientError

from fastapi.testclient import TestClient
from PIL import Image

from app.deepfakeAI_analysis.service import (analyse_deepfakeAI, final_result, UNCERTAIN_EXPLANATION)
from app.auth.dependencies import get_current_user, get_verified_user
from app.main import app

# Test Image
IMAGE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "test.jpg",
)


# ---------------------------------------------------------------------------
# Test 1: Test the analysis service directly.
#
# This bypasses FastAPI and authentication and checks that:
#   image -> service.py -> Model + Gemini -> result
#
# WARNING: This test consumes an Gemini API usage
# ---------------------------------------------------------------------------

def test_analyse_deepfakeAI():
    with Image.open(IMAGE_PATH) as source:
        image = source.convert("RGB")

    result = analyse_deepfakeAI(image)

    # The service must return one of its supported final labels.
    assert result["label"] in {"Real", "Fake", "Uncertain"}

    # The explanation field must always be present.
    assert "explanation" in result
    explanation = result["explanation"]

    assert isinstance(explanation, dict)
    assert set(explanation) == {
        "visual_evidence",
        "reasoning",
        "limitations",
    }

    if result["label"] == "Uncertain":
        # Uncertain results deliberately have no numeric scores.
        assert result["confidence"] is None
        assert result["real_probability"] is None
        assert result["fake_probability"] is None

        assert isinstance(explanation["reasoning"], str)
        assert explanation["reasoning"].strip()

    else:
        # A conclusive result must contain valid detector scores.
        assert isinstance(result["confidence"], (int, float))
        assert 0.0 <= result["confidence"] <= 1.0

        assert isinstance(result["real_probability"], (int, float))
        assert 0.0 <= result["real_probability"] <= 1.0

        assert isinstance(result["fake_probability"], (int, float))
        assert 0.0 <= result["fake_probability"] <= 1.0

        # A conclusive result must include Gemini's explanation.
        assert isinstance(explanation["visual_evidence"], list)
        assert all(
            isinstance(item, str)
            for item in explanation["visual_evidence"]
        )

        assert isinstance(explanation["reasoning"], str)
        assert explanation["reasoning"].strip()

        assert isinstance(explanation["limitations"], str)
        assert explanation["limitations"].strip()


# ---------------------------------------------------------------------------
# Test 2: Test the final output when the detector and Gemini agree.
#
# We do not want this test to load the real detector or make a live Gemini
# API request. Instead, we provide predictable results from both systems
# directly to final_result().
#
# This checks:
#   Detector predicts Fake -> Gemini agrees -> final result is Fake
#   -> detector scores are preserved -> Gemini explanation is returned
# ---------------------------------------------------------------------------

def test_deepfake_AI_agreement_output():
    # Simulate a detector result.
    detector_result = {
        "label": "Fake",
        "confidence": 0.9,
        "real_probability": 0.1,
        "fake_probability": 0.9,
    }

    # Simulate Gemini agreeing with the detector's Fake prediction.
    gemini_result = {
        "assessment": "AI-generated/AI-deepfake",
        "agreement": "Agree",
        "visual_evidence": [
            "Example visual observation supporting the assessment."
        ],
        "reasoning": "Gemini's assessment supports the detector's prediction.",
        "limitations": "Visual inspection alone cannot establish authenticity.",
    }

    result = final_result(detector_result, gemini_result)

    # The final classification and detector scores must be preserved.
    assert result["label"] == "Fake"
    assert result["confidence"] == 0.9
    assert result["real_probability"] == 0.1
    assert result["fake_probability"] == 0.9

    # The final result must contain the structured Gemini explanation.
    assert result["explanation"] == {
        "visual_evidence": [
            "Example visual observation supporting the assessment."
        ],
        "reasoning": "Gemini's assessment supports the detector's prediction.",
        "limitations": "Visual inspection alone cannot establish authenticity.",
    }


# ---------------------------------------------------------------------------
# Test 3: Test the final output when the detector and Gemini disagree.
#
# We do not want this test to load the real detector or make a live Gemini
# API request. Instead, we provide predictable, conflicting results from
# both systems directly to final_result().
#
# This checks:
#   Detector predicts Fake -> Gemini predicts Real and disagrees
#   -> final result is Uncertain -> all classification scores are None
#   -> the generic uncertainty explanation is returned
# ---------------------------------------------------------------------------

def test_deepfake_AI_disagreement_output():
    # Simulate a detector result predicting Fake.
    detector_result = {
        "label": "Fake",
        "confidence": 0.9,
        "real_probability": 0.1,
        "fake_probability": 0.9,
    }

    # Simulate Gemini assessing the image as Real and disagreeing.
    gemini_result = {
        "assessment": "Real",
        "agreement": "Disagree",
        "visual_evidence": [
            "Example visual observation supporting a Real assessment."
        ],
        "reasoning": "Gemini's assessment conflicts with the detector.",
        "limitations": "Visual inspection alone cannot establish authenticity.",
    }

    result = final_result(detector_result, gemini_result)

    # Conflicting classifications must produce an Uncertain result.
    assert result["label"] == "Uncertain"

    # Detector scores must not be exposed when the systems disagree.
    assert result["confidence"] is None
    assert result["real_probability"] is None
    assert result["fake_probability"] is None

    # The generic uncertainty explanation must replace Gemini's explanation.
    assert result["explanation"] == {
        "visual_evidence": None,
        "reasoning": UNCERTAIN_EXPLANATION,
        "limitations": None,
    }


# ---------------------------------------------------------------------------
# Test 4: Test the FastAPI deepfake_AI endpoint.
#
# The real endpoint requires Firebase authentication. We do not want this
# test to depend on a real Firebase token, so get_verified_user is replaced
# with a fake authenticated user for the duration of this test.
#
# This checks:
#   image -> FastAPI router -> service.py -> Model -> JSON response
# ---------------------------------------------------------------------------

def test_deepfake_AI_endpoint(signed_analysis, monkeypatch):
    # Create a fake authenticated user for this test.
    store, identity = signed_analysis
    fake_user = identity["user"]
    
    from app.routers import deepfakeAI_analysis as deepfakeAI_router

    monkeypatch.setattr(
        deepfakeAI_router,
        "get_analysis_store",
        lambda: store,
    )
    
    # Replace the real Firebase authentication dependency.
    app.dependency_overrides[get_verified_user] = lambda: fake_user

    try:
        client = TestClient(app)

        with open(IMAGE_PATH, "rb") as image_file:
            response = client.post(
                "/analysis/deepfakeAI",
                files={
                    "image": (
                        "test.jpg",
                        image_file,
                        "image/jpeg",
                    )
                },
                data={"filename": "test.jpg"},
            )

        assert response.status_code == 200, response.text

        result = response.json()

        assert result["filename"] == "test.jpg"
        assert result["label"] in {"Real", "Fake", "Uncertain"}

        # Uncertain results must not contain classification scores.
        if result["label"] == "Uncertain":
            assert result["confidence"] is None
            assert result["real_probability"] is None
            assert result["fake_probability"] is None
        else:
            assert 0.0 <= result["confidence"] <= 1.0
            assert 0.0 <= result["real_probability"] <= 1.0
            assert 0.0 <= result["fake_probability"] <= 1.0

        # Verify the new structured explanation output.
        assert result["explanation"] is not None
        assert isinstance(result["explanation"], dict)

        explanation = result["explanation"]

        assert isinstance(explanation["reasoning"], str)
        assert explanation["reasoning"].strip()

        # These fields may legitimately be None.
        assert (
            explanation["visual_evidence"] is None
            or isinstance(explanation["visual_evidence"], list)
        )
        assert (
            explanation["limitations"] is None
            or isinstance(explanation["limitations"], str)
        )


    finally:
        # Remove the authentication override so it cannot affect any
        # other tests that run after this one.
        app.dependency_overrides.pop(get_verified_user, None)
        app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Test 5: Test idempotent retries for the FastAPI deepfake endpoint.
#
# A client may retry an image submission if it does not receive the original
# response. Reusing the same Idempotency-Key should return the previously
# saved result instead of running the model or charging the allowance again.
#
# The detector is replaced with a predictable fake implementation so this
# test does not need to load the real model or depend on model predictions.
# The signed_analysis fixture provides an authenticated test user and store.
#
# This checks:
#    First image request -> analysis saved -> same request retried
#    -> same result returned -> detector runs once -> allowance charged once
# ---------------------------------------------------------------------------


def test_deepfake_AI_endpoint_idempotent_retry(signed_analysis, monkeypatch):
    from app.routers import deepfakeAI_analysis as deepfakeAI_router

    store, _ = signed_analysis
    monkeypatch.setattr(
        deepfakeAI_router,
        "get_analysis_store",
        lambda: store,
    )

    detector_calls = 0

    def fake_analyse(image):
        nonlocal detector_calls
        detector_calls += 1    
        return {
            "label": "Fake",
            "confidence": 0.9,
            "real_probability": 0.1,
            "fake_probability": 0.9,
            "explanation": {
                "visual_evidence": [
                    "Example visual evidence for the test."
                ],
                "reasoning": "The test detector classified the image as Fake.",
                "limitations": "This is a predictable test result, not a real analysis.",
            },
        }


    monkeypatch.setattr(
        deepfakeAI_router,
        "analyse_deepfakeAI",
        fake_analyse,
    )

    request_key = "deepfake-idempotency-retry-test"
    headers = {"Idempotency-Key": request_key}
    with open(IMAGE_PATH, "rb") as image_file:
        image_bytes = image_file.read()

        with TestClient(app) as client:
            first = client.post(
                "/analysis/deepfakeAI",
                files={
                    "image": ("test.jpg", image_bytes, "image/jpeg")
                },
                data={"filename": "test.jpg"},
                headers=headers,
            )
            second = client.post(
                "/analysis/deepfakeAI",
                files={
                    "image": ("test.jpg", image_bytes, "image/jpeg")
                },
                data={"filename": "test.jpg"},
                headers=headers,
            )

        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text

        # A retry with the same key returns the saved result.
        assert second.json() == first.json()

        assert first.json()["filename"] == "test.jpg"
        assert second.json()["filename"] == "test.jpg"

        # The detector only ran for the first request.
        assert detector_calls == 1

        result_id = first.json()["result_id"]
        assert (
            store.documents["analysis_results", result_id]["user_id"]
            == "analysis-user"
        )

        # The successful analysis only consumes one allowance.
        allowance = store.documents["usage_allowances", "analysis-user"]
        assert allowance["successful_submissions"] == 1
        assert allowance["remaining_submissions"] == 0


# ---------------------------------------------------------------------------
# Test 6: An invalid Gemini API key must fail the analysis.
#
# We simulate Gemini rejecting the API key so this test does not require
# a real Gemini API call or changes to the .env file.
# ---------------------------------------------------------------------------
def test_invalid_gemini_api_key_fails_analysis():
    image = Image.new("RGB", (100, 100), color="white")

    detector_result = {
        "label": "Fake",
        "confidence": 0.95,
        "real_probability": 0.05,
        "fake_probability": 0.95,
    }

    with (
        patch(
            "app.deepfakeAI_analysis.service.score_deepfakeAI",
            return_value=detector_result,
        ),
        patch(
            "app.deepfakeAI_analysis.service.analyse_with_gemini",
            side_effect=ClientError(
                400,
                {
                    "error": {
                        "code": 400,
                        "message": "API key not valid.",
                        "status": "INVALID_ARGUMENT",
                    }
                },
            ),
        ),
    ):
        with pytest.raises(ClientError):
            analyse_deepfakeAI(image)