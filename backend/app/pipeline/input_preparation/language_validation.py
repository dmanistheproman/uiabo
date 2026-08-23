"""English-language validation for the uiabo Sprint 1 pipeline.

Reference implementation provided by a teammate (docs/input_preparation_additionals)
and integrated into input preparation by Wong Yi Da.

This module distinguishes three outcomes:

* supported: the detector is sufficiently confident that the text is English;
* unsupported: the detector is sufficiently confident it is another language;
* uncertain: the text is too short or ambiguous to label reliably.

It deliberately does not return English merely because Sprint 1 is configured
for English. The detected language and configured processing language are two
different facts.
"""

from dataclasses import dataclass
from enum import Enum

from lingua import Language, LanguageDetectorBuilder


SUPPORTED_LANGUAGE = Language.ENGLISH
SUPPORTED_LANGUAGE_CODE = "en"

# Very small inputs cannot be detected reliably. Returning ``uncertain`` is
# safer than rejecting a valid English word or pretending another language is
# English. This counts alphabetic characters rather than raw string length.
DEFAULT_MINIMUM_LETTERS = 4

# Lingua confidence values are relative scores, not calibrated probabilities.
# Both a minimum best score and separation from the runner-up are required.
# When all spoken languages are compared, the best language can have a modest
# absolute score even when it is clearly ahead of every alternative. The
# separation from the runner-up is therefore the stronger signal.
DEFAULT_MINIMUM_CONFIDENCE = 0.10
DEFAULT_MINIMUM_MARGIN = 0.05

# All spoken languages are included so that French, Malay, Indonesian, Tamil,
# and other submissions are not forced into the small set {English, Chinese}.
_DETECTOR = LanguageDetectorBuilder.from_all_spoken_languages().build()


class LanguageStatus(str, Enum):
    """Result status for the Sprint 1 English-only pipeline."""

    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True, slots=True)
class LanguageValidationResult:
    """Structured result returned to input preparation."""

    status: LanguageStatus
    detected_language: str
    confidence: float | None
    confidence_margin: float | None
    supported: bool
    warning: str | None


class LanguageValidationError(ValueError):
    """The text cannot continue through the English-only pipeline."""

    def __init__(self, message: str, error_code: str) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.http_status = 422


def validate_english(
    text: str,
    *,
    minimum_letters: int = DEFAULT_MINIMUM_LETTERS,
    minimum_confidence: float = DEFAULT_MINIMUM_CONFIDENCE,
    minimum_margin: float = DEFAULT_MINIMUM_MARGIN,
) -> LanguageValidationResult:
    """Determine whether ``text`` is confidently English.

    The function does not mutate the submitted text. It returns ``uncertain``
    for inputs that are too short or where the leading language candidates are
    too close.

    Args:
        text: Submitted text after basic whitespace validation.
        minimum_letters: Minimum alphabetic characters needed for detection.
        minimum_confidence: Required confidence score for the leading language.
        minimum_margin: Required difference between the top two candidates.

    Raises:
        TypeError: If ``text`` is not a string.
        ValueError: If configuration values are invalid.
    """
    if not isinstance(text, str):
        raise TypeError("Text must be a string.")

    if minimum_letters < 1:
        raise ValueError("minimum_letters must be at least 1.")
    if not 0.0 <= minimum_confidence <= 1.0:
        raise ValueError("minimum_confidence must be between 0 and 1.")
    if not 0.0 <= minimum_margin <= 1.0:
        raise ValueError("minimum_margin must be between 0 and 1.")

    letter_count = sum(character.isalpha() for character in text)
    if letter_count < minimum_letters:
        return LanguageValidationResult(
            status=LanguageStatus.UNCERTAIN,
            detected_language="und",
            confidence=None,
            confidence_margin=None,
            supported=False,
            warning=(
                "The text is too short to confirm that it is English."
            ),
        )

    confidence_values = _DETECTOR.compute_language_confidence_values(text)
    if not confidence_values:
        return _uncertain_result(
            "The language could not be determined reliably."
        )

    best = confidence_values[0]
    second_score = (
        confidence_values[1].value
        if len(confidence_values) > 1
        else 0.0
    )
    margin = best.value - second_score

    if best.value < minimum_confidence or margin < minimum_margin:
        return LanguageValidationResult(
            status=LanguageStatus.UNCERTAIN,
            detected_language=_language_code(best.language),
            confidence=round(best.value, 4),
            confidence_margin=round(margin, 4),
            supported=False,
            warning=(
                "The text may be English, but the language result is not "
                "confident enough for the English-only pipeline."
            ),
        )

    detected_code = _language_code(best.language)
    if best.language == SUPPORTED_LANGUAGE:
        return LanguageValidationResult(
            status=LanguageStatus.SUPPORTED,
            detected_language=detected_code,
            confidence=round(best.value, 4),
            confidence_margin=round(margin, 4),
            supported=True,
            warning=None,
        )

    return LanguageValidationResult(
        status=LanguageStatus.UNSUPPORTED,
        detected_language=detected_code,
        confidence=round(best.value, 4),
        confidence_margin=round(margin, 4),
        supported=False,
        warning=(
            f"Sprint 1 supports English only; detected '{detected_code}'."
        ),
    )


def require_english(text: str) -> LanguageValidationResult:
    """Return a supported result or raise a controlled API-style error."""
    result = validate_english(text)

    if result.status is LanguageStatus.SUPPORTED:
        return result

    if result.status is LanguageStatus.UNSUPPORTED:
        raise LanguageValidationError(
            result.warning
            or "Sprint 1 currently supports English text only.",
            error_code="UNSUPPORTED_LANGUAGE",
        )

    raise LanguageValidationError(
        result.warning
        or "The submitted language could not be confirmed.",
        error_code="LANGUAGE_UNCERTAIN",
    )


def _uncertain_result(warning: str) -> LanguageValidationResult:
    return LanguageValidationResult(
        status=LanguageStatus.UNCERTAIN,
        detected_language="und",
        confidence=None,
        confidence_margin=None,
        supported=False,
        warning=warning,
    )


def _language_code(language: Language) -> str:
    """Return an ISO 639-1 code, falling back to Lingua's enum name."""
    iso_code = language.iso_code_639_1
    if iso_code is not None:
        return iso_code.name.lower()
    return language.name.lower()
