import json
import os
from types import SimpleNamespace
from io import BytesIO

import pytest
from PIL import Image

from app.image_context_analysis import extraction_service
from app.image_context_analysis import analysis_service

from fastapi.testclient import TestClient

from app.main import app
from app.auth.dependencies import get_verified_user, get_current_user
from app.routers import image_context_analysis as image_context_router


# --------------------------------------------------
# Test image paths
# --------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

IMAGE_PATH = os.path.join(BASE_DIR, "test.jpg")


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def make_response(payload):
    """Create a lightweight mock of a Gemini response."""
    return SimpleNamespace(text=json.dumps(payload))

def make_test_image():
    """Create a small in-memory image for tests that need no file."""
    return Image.new("RGB", (32, 32), color="white")

TEST_IMAGE_FILENAME = "test.jpg"

MOCK_TAVILY_RESULTS = [
    {
        "title": "Example Source A",
        "url": "https://example.com/source-a",
        "content": "The source provides information relevant to the claim.",
        "score": 0.95,
    },
    {
        "title": "Example Source B",
        "url": "https://example.com/source-b",
        "content": "This source provides additional context.",
        "score": 0.85,
    },
]

MOCK_GEMINI_ANALYSIS = {
    "concern_label": "Needs Caution",
    "explanation": (
        "The available evidence provides some context, "
        "but further verification is needed."
    ),
    "evidence_links": [
        {
            "url": "https://example.com/source-a",
            "relationship": "context",
            "summary": "Provides relevant context for the claim.",
        }
    ],
}


def mock_analysis_gemini(
    monkeypatch,
    payload=None,
    exception=None,
):
    """Mock the second Gemini call used by analysis_service."""

    response = make_response(
        payload if payload is not None else MOCK_GEMINI_ANALYSIS
    )

    def fake_generate_content(**kwargs):
        if exception is not None:
            raise exception
        return response

    monkeypatch.setattr(
        analysis_service.client.models,
        "generate_content",
        fake_generate_content,
    )


def mock_tavily_search(monkeypatch, results=None, exception=None):
    """Mock the Tavily search helper without making an HTTP request."""

    def fake_search(main_claim):
        if exception is not None:
            raise exception
        return results if results is not None else MOCK_TAVILY_RESULTS

    monkeypatch.setattr(
        analysis_service,
        "_search_tavily",
        fake_search,
    )


def assert_gemini_not_called(monkeypatch):
    """Make a test fail if the second Gemini call is attempted."""

    def unexpected_call(**kwargs):
        raise AssertionError(
            "Gemini should not be called in this test."
        )

    monkeypatch.setattr(
        analysis_service.client.models,
        "generate_content",
        unexpected_call,
    )


def run_mocked_analysis(
    image,
    extracted_caption=(
        "A major earthquake hit Singapore this morning."
    ),
    main_claim=(
        "A major earthquake hit Singapore this morning."
    ),
):
    """Run analysis with a supplied image and default test inputs."""

    return analysis_service.analyse_image_context(
        image=image,
        extracted_caption=extracted_caption,
        main_claim=main_claim,
        image_filename=TEST_IMAGE_FILENAME,
    )


def setup_image_context_endpoint_test(
    signed_analysis,
    monkeypatch,
    extraction_error=None,
    analysis_error=None,
):
    """Set up a mocked, authenticated Image Context endpoint test."""

    store, identity = signed_analysis
    fake_user = identity["user"]

    monkeypatch.setattr(
        image_context_router,
        "get_analysis_store",
        lambda: store,
    )

    calls = {"extraction": 0, "analysis": 0}

    def fake_extract_caption(image):
        calls["extraction"] += 1

        if extraction_error is not None:
            raise extraction_error

        return {
            "status": "completed",
            "extracted_caption": (
                "A major earthquake hit Singapore this morning."
            ),
            "main_claim": (
                "A major earthquake hit Singapore this morning."
            ),
        }

    def fake_analyse_image_context(
        image,
        extracted_caption,
        main_claim,
        image_filename,
    ):
        calls["analysis"] += 1

        if analysis_error is not None:
            raise analysis_error

        return {
            "status": "completed",
            "concern_label": "Needs Caution",
            "explanation": "Further verification is needed.",
            "evidence_links": [
                {
                    "title": "Example Source A",
                    "url": "https://example.com/source-a",
                    "relationship": "context",
                    "summary": "Provides relevant context for the claim.",
                }
            ],
            "image_filename": image_filename,
            "extracted_caption": extracted_caption,
        }

    monkeypatch.setattr(
        image_context_router,
        "extract_caption",
        fake_extract_caption,
    )
    monkeypatch.setattr(
        image_context_router,
        "analyse_image_context",
        fake_analyse_image_context,
    )

    app.dependency_overrides[get_verified_user] = lambda: fake_user

    return store, calls


def make_image_upload_bytes():
    image = make_test_image()
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Test 1: Test the service directly:
#   Gemini extraction + Tavily + Gemini analysis.
#
# This bypasses FastAPI and authentication and checks that:
#   image -> extraction_service.py -> Gemini -> analysis_service.py ->
#   Tavily + Gemini -> result
#
# WARNING: This test consumes one Tavily API usage and 2 Gemini API usages
# 
# - Uncomment print statements to view results of the analysis if testing
# service's performance/results.
# - Change test.jpg in this directory to try different images
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not extraction_service.API_KEY
    or not analysis_service.TAVILY_API_KEY,
    reason="Both GEMINI_API_KEY and TAVILY_API_KEY are required.",
)
def test_live_image_context_analysis():
    assert os.path.isfile(IMAGE_PATH), (
        f"Test image not found: {IMAGE_PATH}"
    )

    with Image.open(IMAGE_PATH) as image:
        # First Gemini call: extract caption and main claim.
        extraction = extraction_service.extract_caption(image)

        #print("\n========== LIVE EXTRACTION ==========")
        #print(json.dumps(extraction, indent=2, ensure_ascii=False))

        assert extraction["status"] == "completed"
        assert isinstance(extraction["extracted_caption"], str)
        assert isinstance(extraction["main_claim"], str)

        assert extraction["extracted_caption"].strip(), (
            "The live test image should contain a visible caption."
        )
        assert extraction["main_claim"].strip(), (
            "The live test image should contain an identifiable "
            "factual claim."
        )

        # Tavily search: print the raw search results.
        tavily_results = analysis_service._search_tavily(
            extraction["main_claim"]
        )

        #print("\n========== LIVE TAVILY RESULTS ==========")
        #print(json.dumps(tavily_results, indent=2, ensure_ascii=False))

        # Tavily search + second Gemini call.
        analysis = analysis_service.analyse_image_context(
            image=image,
            extracted_caption=extraction["extracted_caption"],
            main_claim=extraction["main_claim"],
            image_filename=os.path.basename(IMAGE_PATH),
        )

    #print("\n========== LIVE FINAL ANALYSIS ==========")
    #print(json.dumps(analysis, indent=2, ensure_ascii=False))

    assert analysis["status"] == "completed"
    assert analysis["concern_label"] in {
        "Low Concern",
        "Needs Caution",
        "High Concern",
        "Not Enough Information",
    }
    assert isinstance(analysis["explanation"], str)
    assert isinstance(analysis["evidence_links"], list)
    assert len(analysis["evidence_links"]) <= 2
    assert analysis["image_filename"] == os.path.basename(IMAGE_PATH)
    assert (
        analysis["extracted_caption"]
        == extraction["extracted_caption"]
    )


# ---------------------------------------------------------------------------
# Test 2: Tavily succeeds and Gemini produces the final result.
#
# Both services are mocked. No API calls or API credits are used.
# ---------------------------------------------------------------------------

def test_analysis_tavily_success(monkeypatch):
    mock_tavily_search(monkeypatch)
    mock_analysis_gemini(monkeypatch)

    result = run_mocked_analysis(make_test_image())

    assert result["status"] == "completed"
    assert result["concern_label"] == "Needs Caution"
    assert result["explanation"]

    assert result["image_filename"] == TEST_IMAGE_FILENAME
    assert (
        result["extracted_caption"]
        == "A major earthquake hit Singapore this morning."
    )

    assert len(result["evidence_links"]) == 1
    assert (
        result["evidence_links"][0]["url"]
        == "https://example.com/source-a"
    )
    assert (
        result["evidence_links"][0]["title"]
        == "Example Source A"
    )


# ---------------------------------------------------------------------------
# Test 3: Tavily fails.
#
# The service must return Not enough information and skip Gemini.
# ---------------------------------------------------------------------------

def test_analysis_tavily_failure(monkeypatch):
    mock_tavily_search(
        monkeypatch,
        exception=RuntimeError("Simulated Tavily failure"),
    )
    assert_gemini_not_called(monkeypatch)

    result = run_mocked_analysis(make_test_image())

    assert result["status"] == "completed"
    assert result["concern_label"] == "Not Enough Information"
    assert result["evidence_links"] == []
    assert result["image_filename"] == TEST_IMAGE_FILENAME
    assert "search service" in result["explanation"].lower()


# ---------------------------------------------------------------------------
# Test 4: Tavily succeeds but returns no usable results.
#
# Gemini must not be called when there is no usable evidence.
# ---------------------------------------------------------------------------

def test_analysis_tavily_no_usable_results(monkeypatch):
    mock_tavily_search(monkeypatch, results=[])
    assert_gemini_not_called(monkeypatch)

    result = run_mocked_analysis(make_test_image())

    assert result["status"] == "completed"
    assert result["concern_label"] == "Not Enough Information"
    assert result["evidence_links"] == []
    assert "usable evidence" in result["explanation"].lower()


# ---------------------------------------------------------------------------
# Test 5: The main claim is empty.
#
# Neither Tavily nor Gemini should be called.
# ---------------------------------------------------------------------------

def test_analysis_empty_main_claim(monkeypatch):
    def unexpected_search(main_claim):
        raise AssertionError(
            "Tavily should not be called for an empty main claim."
        )

    monkeypatch.setattr(
        analysis_service,
        "_search_tavily",
        unexpected_search,
    )
    assert_gemini_not_called(monkeypatch)

    result = run_mocked_analysis(
        make_test_image(),
        extracted_caption="Some caption without a verifiable claim.",
        main_claim="   ",
    )

    assert result["status"] == "completed"
    assert result["concern_label"] == "Not Enough Information"
    assert result["evidence_links"] == []
    assert (
        result["extracted_caption"]
        == "Some caption without a verifiable claim."
    )
    assert "no identifiable factual claim" in (
        result["explanation"].lower()
    )


# ---------------------------------------------------------------------------
# Test 6: Tavily API key is missing.
#
# This uses the real _search_tavily helper but makes no HTTP request,
# because the missing-key check occurs before the request.
# Gemini must not be called.
# ---------------------------------------------------------------------------

def test_analysis_missing_tavily_api_key(monkeypatch):
    monkeypatch.setattr(
        analysis_service,
        "TAVILY_API_KEY",
        None,
    )
    assert_gemini_not_called(monkeypatch)

    result = run_mocked_analysis(make_test_image())

    assert result["status"] == "completed"
    assert result["concern_label"] == "Not Enough Information"
    assert result["evidence_links"] == []
    assert "search service" in result["explanation"].lower()


# ---------------------------------------------------------------------------
# Test 7: An invalid Gemini API key must fail the analysis.
#
# We simulate Gemini rejecting the API key so this test does not require
# a real Gemini API call or changes to the .env file.
# ---------------------------------------------------------------------------

def test_extract_caption_missing_api_key(monkeypatch):
    monkeypatch.setattr(extraction_service, "API_KEY", None)

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        extraction_service.extract_caption(make_test_image())



# ---------------------------------------------------------------------------
# Test 8: Test the authenticated Check Image Context endpoint.
#
# Both analysis stages are mocked so this test makes no real API calls.
#
# Checks:
#   image -> FastAPI router -> extraction -> analysis -> saved JSON response
# ---------------------------------------------------------------------------

def test_image_context_endpoint(signed_analysis, monkeypatch):
    store, identity = signed_analysis
    fake_user = identity["user"]

    monkeypatch.setattr(
        image_context_router,
        "get_analysis_store",
        lambda: store,
    )

    store, calls = setup_image_context_endpoint_test(
        signed_analysis,
        monkeypatch,
    )

    app.dependency_overrides[get_verified_user] = lambda: fake_user

    try:
        with TestClient(app) as client:
            with open(IMAGE_PATH, "rb") as image_file:
                response = client.post(
                    "/analysis/image-context",
                    files={
                        "image": (
                            "test.jpg",
                            image_file,
                            "image/jpeg",
                        )
                    },
                    data={"filename": "test.jpg"},
                    headers={
                        "Idempotency-Key": "image-context-endpoint-test",
                    },
                )

        assert response.status_code == 200, response.text

        result = response.json()

        assert result["processing_status"] == "completed"
        assert result["input_type"] == "image_context"
        assert result["image_filename"] == "test.jpg"
        assert result["extracted_caption"] == (
            "A major earthquake hit Singapore this morning."
        )
        assert result["concern_label"] == "Needs Caution"

        assert isinstance(result["explanation"], str)
        assert result["explanation"].strip()

        assert isinstance(result["evidence_links"], list)
        assert len(result["evidence_links"]) == 1

        link = result["evidence_links"][0]
        assert link["title"] == "Example Source A"
        assert link["url"] == "https://example.com/source-a"
        assert link["relationship"] == "context"
        assert link["summary"]

        # Both stages ran exactly once.
        assert calls["extraction"] == 1
        assert calls["analysis"] == 1

        # The result was saved for the authenticated user.
        result_id = result["result_id"]
        saved_record = store.documents[
            ("analysis_results", result_id)
        ]
        assert saved_record["user_id"] == "analysis-user"

    finally:
        app.dependency_overrides.pop(get_verified_user, None)
        app.dependency_overrides.pop(get_current_user, None)

# ---------------------------------------------------------------------------
# Test 9: Test idempotent retries for Check Image Context.
#
# Repeating the same image submission with the same Idempotency-Key should
# return the saved result without rerunning either analysis stage or charging
# the allowance again.
# ---------------------------------------------------------------------------

def test_image_context_endpoint_idempotent_retry(
    signed_analysis,
    monkeypatch,
):
    store, identity = signed_analysis
    fake_user = identity["user"]

    monkeypatch.setattr(
        image_context_router,
        "get_analysis_store",
        lambda: store,
    )

    store, calls = setup_image_context_endpoint_test(
        signed_analysis,
        monkeypatch,
    )

    app.dependency_overrides[get_verified_user] = lambda: fake_user

    request_key = "image-context-idempotency-retry-test"
    headers = {"Idempotency-Key": request_key}

    try:
        with open(IMAGE_PATH, "rb") as image_file:
            image_bytes = image_file.read()

        with TestClient(app) as client:
            first = client.post(
                "/analysis/image-context",
                files={
                    "image": (
                        "test.jpg",
                        image_bytes,
                        "image/jpeg",
                    )
                },
                data={"filename": "test.jpg"},
                headers=headers,
            )

            second = client.post(
                "/analysis/image-context",
                files={
                    "image": (
                        "test.jpg",
                        image_bytes,
                        "image/jpeg",
                    )
                },
                data={"filename": "test.jpg"},
                headers=headers,
            )

        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text

        first_result = first.json()
        second_result = second.json()

        # The retry returns the original saved result.
        assert second_result == first_result
        assert first_result["image_filename"] == "test.jpg"
        assert second_result["image_filename"] == "test.jpg"

        # Neither stage runs again for the retry.
        assert calls["extraction"] == 1
        assert calls["analysis"] == 1

        result_id = first_result["result_id"]
        saved_record = store.documents[
            ("analysis_results", result_id)
        ]
        assert saved_record["user_id"] == "analysis-user"

        # The successful analysis consumes one allowance only.
        allowance = store.documents[
            ("usage_allowances", "analysis-user")
        ]
        assert allowance["successful_submissions"] == 1
        assert allowance["remaining_submissions"] == 0

    finally:
        app.dependency_overrides.pop(get_verified_user, None)
        app.dependency_overrides.pop(get_current_user, None)

# ---------------------------------------------------------------------------
# Test 10: Caption extraction fails.
#
# The first Gemini call fails, so the allowance must remain unchanged.
# ---------------------------------------------------------------------------

def test_image_context_extraction_failure_no_allowance(
    signed_analysis,
    monkeypatch,
):
    store, calls = setup_image_context_endpoint_test(
        signed_analysis,
        monkeypatch,
        extraction_error=RuntimeError(
            "Simulated caption extraction failure"
        ),
    )

    try:
        with TestClient(app) as client:
            response = client.post(
                "/analysis/image-context",
                files={
                    "image": (
                        "test.jpg",
                        make_image_upload_bytes(),
                        "image/jpeg",
                    )
                },
                data={"filename": "test.jpg"},
                headers={
                    "Idempotency-Key": (
                        "image-context-extraction-failure-test"
                    )
                },
            )

        assert response.status_code == 503, response.text

        assert calls["extraction"] == 1
        assert calls["analysis"] == 0

        allowance = store.documents[
            ("usage_allowances", "analysis-user")
        ]

        assert allowance["successful_submissions"] == 0
        assert allowance["remaining_submissions"] == 1

    finally:
        app.dependency_overrides.pop(get_verified_user, None)
        app.dependency_overrides.pop(get_current_user, None)

# ---------------------------------------------------------------------------
# Test 11: Caption extraction succeeds but final analysis fails.
#
# The first Gemini call succeeded, so one allowance must be deducted even
# though the overall endpoint returns a failure response.
# ---------------------------------------------------------------------------

def test_image_context_analysis_failure_charges_allowance(
    signed_analysis,
    monkeypatch,
):
    store, calls = setup_image_context_endpoint_test(
        signed_analysis,
        monkeypatch,
        analysis_error=RuntimeError(
            "Simulated final analysis failure"
        ),
    )

    try:
        with TestClient(app) as client:
            response = client.post(
                "/analysis/image-context",
                files={
                    "image": (
                        "test.jpg",
                        make_image_upload_bytes(),
                        "image/jpeg",
                    )
                },
                data={"filename": "test.jpg"},
                headers={
                    "Idempotency-Key": (
                        "image-context-final-analysis-failure-test"
                    )
                },
            )

        assert response.status_code == 503, response.text

        assert calls["extraction"] == 1
        assert calls["analysis"] == 1

        allowance = store.documents[
            ("usage_allowances", "analysis-user")
        ]

        assert allowance["successful_submissions"] == 1
        assert allowance["remaining_submissions"] == 0

    finally:
        app.dependency_overrides.pop(get_verified_user, None)
        app.dependency_overrides.pop(get_current_user, None)

# ---------------------------------------------------------------------------
# Test 12: Both caption extraction and final analysis succeed.
#
# A completed analysis must deduct exactly one allowance.
# ---------------------------------------------------------------------------

def test_image_context_success_charges_one_allowance(
    signed_analysis,
    monkeypatch,
):

    store, calls = setup_image_context_endpoint_test(
        signed_analysis,
        monkeypatch,
    )

    try:
        with TestClient(app) as client:
            response = client.post(
                "/analysis/image-context",
                files={
                    "image": (
                        "test.jpg",
                        make_image_upload_bytes(),
                        "image/jpeg",
                    )
                },
                data={"filename": "test.jpg"},
                headers={
                    "Idempotency-Key": (
                        "image-context-success-allowance-test"
                    )
                },
            )

        assert response.status_code == 200, response.text

        result = response.json()
        assert result["processing_status"] == "completed"
        assert result["concern_label"] == "Needs Caution"

        assert calls["extraction"] == 1
        assert calls["analysis"] == 1

        allowance = store.documents[
            ("usage_allowances", "analysis-user")
        ]

        assert allowance["successful_submissions"] == 1
        assert allowance["remaining_submissions"] == 0

    finally:
        app.dependency_overrides.pop(get_verified_user, None)
        app.dependency_overrides.pop(get_current_user, None)