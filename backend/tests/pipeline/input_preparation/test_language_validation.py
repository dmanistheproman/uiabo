"""Tests for English-language validation.

Ported from the teammate's reference tests in
docs/input_preparation_additionals/test_language_validation.py and adapted
to the package layout of the pipeline component.
"""

import pytest

from app.pipeline.input_preparation.language_validation import (
    LanguageStatus,
    LanguageValidationError,
    validate_english,
    require_english,
)


@pytest.mark.parametrize(
    "text",
    [
        "A new community tax will start next week.",
        "The MRT station will open on 1 September 2026.",
        "Singapore residents can apply for the support grant online.",
        "The policy is NOT cancelled.",
    ],
)
def test_clear_english_is_supported(text: str) -> None:
    result = validate_english(text)

    assert result.status is LanguageStatus.SUPPORTED
    assert result.detected_language == "en"
    assert result.supported is True
    assert result.warning is None
    assert result.confidence is not None


@pytest.mark.parametrize(
    "text",
    [
        "Cukai baharu akan bermula minggu depan.",
        "下星期开始征收新税。",
        "அடுத்த வாரம் புதிய வரி தொடங்கும்.",
        "Une nouvelle taxe commencera la semaine prochaine.",
    ],
    ids=["malay", "chinese", "tamil", "french"],
)
def test_clear_non_english_is_not_supported(text: str) -> None:
    result = validate_english(text)

    assert result.status is LanguageStatus.UNSUPPORTED
    assert result.detected_language != "en"
    assert result.supported is False
    assert result.warning is not None


@pytest.mark.parametrize("text", ["No.", "Tax?", "OK", "12345"])
def test_short_or_non_linguistic_text_is_uncertain(text: str) -> None:
    result = validate_english(text)

    assert result.status is LanguageStatus.UNCERTAIN
    assert result.supported is False
    assert result.warning is not None


def test_unsupported_language_raises_controlled_error() -> None:
    with pytest.raises(LanguageValidationError) as raised:
        require_english("下星期开始征收新税。")

    assert raised.value.error_code == "UNSUPPORTED_LANGUAGE"
    assert raised.value.http_status == 422


def test_uncertain_language_raises_different_error() -> None:
    with pytest.raises(LanguageValidationError) as raised:
        require_english("No.")

    assert raised.value.error_code == "LANGUAGE_UNCERTAIN"
    assert raised.value.http_status == 422


def test_supported_language_can_continue() -> None:
    result = require_english(
        "The community event begins on Monday morning."
    )

    assert result.supported is True
    assert result.detected_language == "en"


@pytest.mark.parametrize('text', [
    'Singapore next week will hit 50 degree celcius',
    'Singapore will hit 50 degrees celcius next week',
])
def test_temperature_typo_retries_detection_without_rewriting_claim(text):
    from app.pipeline.input_preparation.service import prepare_text
    result = validate_english(text)
    assert result.supported and result.detected_language == 'en'
    prepared = prepare_text(text)
    assert prepared.original_text == prepared.normalised_text == text


@pytest.mark.parametrize('text', [
    'Singapore suhu 50 darjah celcius minggu depan',
    'Singapore akan mencapai 50 derajat celcius minggu depan',
    '50 celcius',
    'CPF retirement age 75',
])
def test_typo_retry_does_not_admit_other_languages_or_ambiguous_fragments(text):
    assert not validate_english(text).supported


def test_typo_retry_keeps_custom_confidence_requirements():
    assert not validate_english('Singapore next week will hit 50 degree celcius',
                                minimum_margin=.2).supported


def test_language_probe_only_repairs_numeric_units():
    from app.pipeline.input_preparation.language_validation import _language_probe
    assert _language_probe('50 degree celcius') == '50 degree Celsius'
    assert _language_probe('122 degrees farenheit') == '122 degrees Fahrenheit'
    assert _language_probe('A company called Celcius') == 'A company called Celcius'


def test_validation_does_not_modify_the_input() -> None:
    text = "  The policy is NOT cancelled.  "

    validate_english(text)

    assert text == "  The policy is NOT cancelled.  "


def test_non_string_input_is_rejected() -> None:
    with pytest.raises(TypeError):
        validate_english(None)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("keyword", "value"),
    [
        ("minimum_letters", 0),
        ("minimum_confidence", 1.1),
        ("minimum_margin", -0.1),
    ],
)
def test_invalid_configuration_is_rejected(
    keyword: str, value: float
) -> None:
    with pytest.raises(ValueError):
        validate_english(
            "This is a clear English sentence.",
            **{keyword: value},
        )
