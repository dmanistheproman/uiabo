import json
from pathlib import Path

import pytest

from app.pipeline.claim_analysis.service import (
    analyse_claim,
    create_fallback_result,
    select_majority_result,
)
from app.pipeline.shared.models import PreparedText


# --------------------------------------------------
# Load sample dataset
# --------------------------------------------------

SAMPLE_FILE = (
    Path(__file__).resolve().parents[4]
    / "sprint_1_samples"
    / "02_matthew_claim_samples.json"
)


with open(SAMPLE_FILE, "r", encoding="utf-8") as file:
    SAMPLE_DATA = json.load(file)


SAMPLES = SAMPLE_DATA["samples"]


# --------------------------------------------------
# Helper: create a model result for testing
# --------------------------------------------------

def make_result(category: str) -> dict:
    return {
        "extracted_claim": None,
        "claim_category": category,
        "checkable": None,
        "classification_reason": "Test result.",
        "claim_confidence": None,
    }


# --------------------------------------------------
# Test fallback result
# --------------------------------------------------

def test_create_fallback_result():

    result = create_fallback_result()

    assert result["extracted_claim"] is None
    assert result["claim_category"] == "unverifiable"
    assert result["checkable"] is False
    assert result["classification_reason"] == "Error in model output."
    assert result["claim_confidence"] == 0.0


# --------------------------------------------------
# Test majority voting
# --------------------------------------------------

def test_majority_all_agree():

    results = {
        "gpt-oss:120b": make_result("factual"),
        "gemma4:31b": make_result("factual"),
        "nemotron-3-super": make_result("factual"),
    }

    result = select_majority_result(results)

    assert result["claim_category"] == "factual"
    assert result["claim_confidence"] == 1.0


def test_majority_gpt_and_gemma():

    results = {
        "gpt-oss:120b": make_result("factual"),
        "gemma4:31b": make_result("factual"),
        "nemotron-3-super": make_result("opinion"),
    }

    result = select_majority_result(results)

    assert result["claim_category"] == "factual"
    assert result["claim_confidence"] == 0.67


def test_majority_gpt_and_nemotron():

    results = {
        "gpt-oss:120b": make_result("factual"),
        "gemma4:31b": make_result("opinion"),
        "nemotron-3-super": make_result("factual"),
    }

    result = select_majority_result(results)

    assert result["claim_category"] == "factual"
    assert result["claim_confidence"] == 0.67


def test_majority_gemma_and_nemotron():

    results = {
        "gpt-oss:120b": make_result("opinion"),
        "gemma4:31b": make_result("factual"),
        "nemotron-3-super": make_result("factual"),
    }

    result = select_majority_result(results)

    assert result["claim_category"] == "factual"
    assert result["claim_confidence"] == 0.67


def test_majority_no_agreement():

    results = {
        "gpt-oss:120b": make_result("factual"),
        "gemma4:31b": make_result("opinion"),
        "nemotron-3-super": make_result("prediction"),
    }

    result = select_majority_result(results)

    assert result["claim_category"] == "unverifiable"
    assert result["extracted_claim"] is None
    assert result["checkable"] is False
    assert result["claim_confidence"] == 0.0


# --------------------------------------------------
# Test actual sample inputs
# --------------------------------------------------

@pytest.mark.parametrize(
    "sample",
    SAMPLES,
    ids=[sample["scenario_id"] for sample in SAMPLES]
)
def test_sample_input_structure(sample):

    input_data = sample["input"]
    expected = sample["expected_output"]

    prepared_text = PreparedText(**input_data)

    assert prepared_text.original_text == input_data["original_text"]
    assert prepared_text.normalised_text == input_data["normalised_text"]
    assert prepared_text.language == input_data["language"]
    assert prepared_text.warnings == input_data["warnings"]

    assert expected["claim_category"] in {
        "factual",
        "opinion",
        "joke_or_satire",
        "prediction",
        "personal_experience",
        "unverifiable",
    }


# --------------------------------------------------
# Test analyse_claim using sample data
# --------------------------------------------------

@pytest.mark.parametrize(
    "sample",
    SAMPLES,
    ids=[sample["scenario_id"] for sample in SAMPLES]
)
def test_analyse_claim_samples(monkeypatch, sample):

    input_data = sample["input"]
    expected = sample["expected_output"]

    prepared_text = PreparedText(**input_data)

    expected_category = expected["claim_category"]
    expected_claim = expected["extracted_claim"]

    def fake_run_model(model, prepared_text, prompt_type):

        if prompt_type == "CLASSIFICATION":
            return make_result(expected_category)

        if prompt_type == "EXTRACTION":
            return expected_claim

        raise ValueError(f"Unexpected prompt type: {prompt_type}")

    monkeypatch.setattr(
        "app.pipeline.claim_analysis.service.run_model",
        fake_run_model
    )

    result = analyse_claim(prepared_text)

    # Classification
    assert result.claim_category == expected_category

    # Factual claims should be checkable and have an extracted claim
    if expected_category == "factual":
        assert result.checkable is True
        assert result.extracted_claim == expected_claim

    # Non-factual claims should not be checkable
    else:
        assert result.checkable is False
        assert result.extracted_claim is None

    # Confidence comes from model agreement,
    # not from the sample's original confidence value.
    assert result.claim_confidence == 1.0


# --------------------------------------------------
# Test extraction failure
# --------------------------------------------------

def test_extraction_failure(monkeypatch):

    prepared_text = PreparedText(
        original_text="A new $500 community tax starts next week.",
        normalised_text="A new $500 community tax starts next week.",
        language="en",
        warnings=[],
    )

    def fake_run_model(model, prepared_text, prompt_type):

        if prompt_type == "CLASSIFICATION":
            return make_result("factual")

        if prompt_type == "EXTRACTION":
            raise RuntimeError("Extraction model unavailable")

        raise ValueError(f"Unexpected prompt type: {prompt_type}")

    monkeypatch.setattr(
        "app.pipeline.claim_analysis.service.run_model",
        fake_run_model
    )

    result = analyse_claim(prepared_text)

    assert result.claim_category == "factual"
    assert result.extracted_claim is None
    assert result.checkable is False
    assert result.claim_confidence == 1.0


# --------------------------------------------------
# Test classification model failure
# --------------------------------------------------

def test_classification_model_failure(monkeypatch):

    prepared_text = PreparedText(
        original_text="A new $500 community tax starts next week.",
        normalised_text="A new $500 community tax starts next week.",
        language="en",
        warnings=[],
    )

    def fake_run_model(model, prepared_text, prompt_type):
        raise RuntimeError("Classification model unavailable")

    monkeypatch.setattr(
        "app.pipeline.claim_analysis.service.run_model",
        fake_run_model
    )

    result = analyse_claim(prepared_text)

    assert result.claim_category == "unverifiable"
    assert result.extracted_claim is None
    assert result.checkable is False

    # All three models failed, so the fallback confidence
    # should remain 0.0 rather than becoming 1.0.
    assert result.claim_confidence == 0.0