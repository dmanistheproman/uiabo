"""Input preparation for the uiabo text-analysis pipeline.

Owner: Wong Yi Da (Sprint 1). Limitations are recorded in SECURITY.md.

First stage of the pipeline: validates submitted text, normalises it
without changing its meaning, and attaches warnings for anything the
downstream components should treat with suspicion.

Design rule: this component FLAGS, it does not FILTER. Instruction-like
text is warned about and passed through unchanged, because removing it
would delete the claim we are meant to check. The real prompt-injection
defence belongs to the components that build LLM prompts.

Language: Sprint 1 processes English only, but the declared language is
now a detection result rather than an assumption. Text that the detector
cannot confidently attribute to English is rejected, never silently
treated as English. See ``language_validation.py``.

Deliberately not done, because each of these changes meaning: lowercasing,
stopword removal, punctuation stripping, NFKC normalisation.
"""

import re
import unicodedata

from pydantic import BaseModel, Field

from app.pipeline.input_preparation.language_validation import (
    SUPPORTED_LANGUAGE_CODE,
    LanguageValidationError,
    require_english,
)


# Matches the limit enforced by ``TextAnalysisRequest`` in app/schemas.py.
MAX_TEXT_LENGTH = 5000

# Wording is fixed by the Sprint 1 interface; do not reword without team
# agreement (see UIABO_SPRINT_1_TEAM_TASKS.md, "Interface change rule").
INJECTION_WARNING = (
    "Instruction-like content detected; "
    "treat the entire submission as untrusted data."
)

# Hidden-character warning wording is asserted in tests and shared samples.
HIDDEN_CHARACTER_WARNING = (
    "Hidden or invisible formatting characters were removed."
)

# Zero-width joiner (U+200D) and non-joiner (U+200C) are format controls
# that carry real meaning in emoji sequences and several writing systems,
# so they must not be removed by a general formatting-character rule.
_PRESERVED_FORMAT_CHARACTERS = {
    "\u200c",  # ZERO WIDTH NON-JOINER
    "\u200d",  # ZERO WIDTH JOINER
}

# 30 or more of the same character in a row: degenerate filler, not a claim.
_LONG_REPEAT = re.compile(r"(.)\1{29,}")

# Combining marks stacked on one base character ("Zalgo" text). Counted as
# a consecutive run rather than as a share of the text: Arabic with harakat
# and Hebrew with niqqud are legitimately mark-dense but never stack more
# than two or three marks on one base character.
_COMBINING_RUN_LIMIT = 4

# Phrasing that tries to steer the pipeline rather than state a claim.
#
# These patterns are deliberately narrow. Submitted claims are often ABOUT
# rules, systems and policy changes ("a new rules change takes effect
# Monday"), so a loose pattern floods ordinary claims with warnings. Each
# pattern requires something an ordinary third-person claim does not have:
# the system addressed in the second person, a chat role marker, or an
# explicit demand for one of our own verdict labels.
_INJECTION_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        # "ignore all previous instructions", "forget your rules"
        r"\b(ignore|disregard|forget|discard)\b[^.]{0,40}?"
        r"\b(previous|prior|above|earlier|all|your|these|any)\b[^.]{0,20}?"
        r"\b(instruction|instructions|prompt|prompts|rule|rules|"
        r"context|training|guidelines?|directives?)\b",

        # Second-person role reassignment. "act as" and "from now on" are
        # excluded on their own -- both are ordinary English ("banks must
        # act as intermediaries", "the deputy will act as spokesperson
        # from now on").
        r"\b(you are now|from now on,? you|pretend (to be|you)|"
        r"roleplay as|behave like you|act (as|like) (a |an )?"
        r"(helpful |unrestricted |uncensored )*"
        r"(ai|assistant|model|chatbot|language model))\b",

        # Chat role markers, only at the start of a line.
        r"(?m)^\s*(system|assistant|user|developer)\s*:",

        # "system prompt:" as a directive, not as a noun phrase
        # ("the system prompt response time has doubled").
        r"\b(system|developer)\s+prompt\s*:",

        # "follow the new instructions"
        r"\b(new|updated|revised|following)\s+"
        r"(instruction|instructions|prompt|prompts)\b",

        # Dictating one of our own verdict labels.
        r"\b(return|reply with|respond with|output|answer with|say|"
        r"classify (it|this) as|mark (it|this) as)\b"
        r"[^.]{0,30}?\b(low concern|needs caution|high concern|"
        r"not enough information)\b",

        # "override your safety rules". Requires the possessive: "skip the
        # safety checks" is an ordinary claim about the world.
        r"\b(override|bypass|disable|circumvent)\b[^.]{0,20}?"
        r"\byour\b",

        # Chat-template and role markers pasted into user content.
        r"<\|[a-z_]+\|>",
        r"\[/?INST\]",
        r"###\s*(instruction|system|assistant)",
    )
]


class InvalidTextError(ValueError):
    """Submitted text cannot be prepared for analysis.

    Carries the HTTP status and machine-readable code the API should
    surface. Raised instead of returning a ``PreparedText`` so invalid
    input can never reach claim analysis.
    """

    def __init__(
        self,
        message: str,
        error_code: str = "INVALID_TEXT",
        http_status: int = 422,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.http_status = http_status


class PreparedText(BaseModel):
    """Handoff 1: input preparation -> claim analysis.

    Claim analysis reads ``normalised_text`` only. ``original_text`` is
    preserved verbatim so orchestration can store exactly what the user
    submitted.

    Belongs in ``pipeline/shared/`` once the team agrees the integration
    change; it lives here while input preparation is the only owner.
    """

    original_text: str
    normalised_text: str = Field(min_length=1)
    language: str
    warnings: list[str] = Field(default_factory=list)


def prepare_text(text: str) -> PreparedText:
    """Validate and normalise submitted text.

    Raises:
        InvalidTextError: text is not a string, is too long, contains an
            unsafe control character, has no visible characters once hidden
            characters are removed, or is not confidently English
            (``UNSUPPORTED_LANGUAGE`` / ``LANGUAGE_UNCERTAIN``).
    """
    if not isinstance(text, str):
        raise InvalidTextError("Text must be a string.")

    if len(text) > MAX_TEXT_LENGTH:
        raise InvalidTextError(
            f"Text must not exceed {MAX_TEXT_LENGTH} characters.",
            error_code="TEXT_TOO_LONG",
        )

    warnings: list[str] = []

    normalised, removed_formatting = _normalise_characters(text)
    if removed_formatting:
        warnings.append(HIDDEN_CHARACTER_WARNING)

    if not normalised:
        raise InvalidTextError(
            "Text must contain at least one visible character."
        )

    if any(pattern.search(normalised) for pattern in _INJECTION_PATTERNS):
        warnings.append(INJECTION_WARNING)

    if _LONG_REPEAT.search(normalised):
        warnings.append(
            "Text contains a long run of repeated characters."
        )

    if _has_combining_mark_stack(normalised):
        warnings.append(
            "Text contains an unusual number of combining marks."
        )

    # The gate runs last so that every other check sees the same text it
    # would have seen before language validation existed. Only text the
    # detector confidently attributes to English may continue.
    try:
        require_english(normalised)
    except LanguageValidationError as error:
        raise InvalidTextError(
            error.message,
            error_code=error.error_code,
        ) from error

    return PreparedText(
        original_text=text,
        normalised_text=normalised,
        language=SUPPORTED_LANGUAGE_CODE,
        warnings=warnings,
    )


def _normalise_characters(text: str) -> tuple[str, bool]:
    """Normalise Unicode without ever joining two whitespace-separated words.

    The ordering rule is:

    1. normalise Unicode composition (NFC composes accents without
       rewriting compatibility characters, so amounts, symbols and
       full-width forms survive unchanged);
    2. convert every recognised whitespace character to a normal space;
    3. remove invisible formatting characters;
    4. reject unexpected non-whitespace control characters.

    Whitespace is handled before format and control characters because some
    separators such as U+0085 NEXT LINE are category Cc: deleting them as
    controls would silently join two words ("tax\\u0085starts").
    """
    composed = unicodedata.normalize("NFC", text)
    output: list[str] = []
    removed_formatting = False

    for character in composed:
        if character.isspace():
            output.append(" ")
            continue

        category = unicodedata.category(character)

        if category == "Cf":
            if character in _PRESERVED_FORMAT_CHARACTERS:
                output.append(character)
            else:
                removed_formatting = True
            continue

        # Non-whitespace control, surrogate, and unassigned-category control
        # characters must not be silently deleted: their intended boundary
        # is ambiguous and removal could change a claim.
        if category in {"Cc", "Cs"}:
            code_point = f"U+{ord(character):04X}"
            name = unicodedata.name(character, "unnamed control character")
            raise InvalidTextError(
                f"Text contains unsupported control character "
                f"{code_point} ({name}).",
                error_code="UNSAFE_CONTROL_CHARACTER",
            )

        output.append(character)

    # Splitting and joining collapses all runs of ordinary spaces and trims
    # their ends. It is safe now because every recognised Unicode whitespace
    # character has already become an ordinary space.
    return " ".join("".join(output).split()), removed_formatting


def _has_combining_mark_stack(text: str) -> bool:
    """Report whether combining marks are stacked on one base character.

    Run length, not overall share: comparing marks against text length
    flagged correctly spelled Arabic (harakat) and Hebrew (niqqud) as
    degenerate.
    """
    run = 0

    for character in text:
        if unicodedata.combining(character):
            run += 1
            if run >= _COMBINING_RUN_LIMIT:
                return True
        else:
            run = 0

    return False
