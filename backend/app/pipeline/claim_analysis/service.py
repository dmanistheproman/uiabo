"""Validated claim analysis using Matthew's three-model Ollama Cloud ensemble.

The synchronous pipeline boundary runs bounded concurrent cloud requests.
Credentials are loaded only when called, never on import or during unit tests.
"""

import asyncio
from collections import Counter
import json
import os
from pathlib import Path
import re

from dotenv import load_dotenv
import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .categories import CLASSIFICATION_MODELS, EXTRACTION_MODEL, CLASSIFICATION_PROMPT, EXTRACTION_PROMPT
from ..shared.errors import PipelineComponentError
from ..shared.models import ClaimAnalysis, ClaimCategory, PreparedText

PROJECT_ENV = Path(__file__).resolve().parents[4] / ".env"
REQUEST_TIMEOUT_SECONDS = 40.0
TOTAL_TIMEOUT_SECONDS = 90.0


class ClassificationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    claim_category: ClaimCategory
    classification_reason: str = Field(min_length=1, max_length=2000)


class ExtractionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    extracted_claim: str = Field(min_length=3, max_length=5000)


def _error(message: str, code: str, *, retryable: bool = True) -> PipelineComponentError:
    return PipelineComponentError(
        message, error_code=code, stage="claim_analysis", retryable=retryable,
    )


def _api_key() -> str:
    # Explicit deployment/shell configuration takes precedence over local .env.
    load_dotenv(PROJECT_ENV, override=False)
    key = os.environ.get("OLLAMA_API_KEY", "").strip()
    if not key:
        raise _error("Claim analysis is not configured.",
                     "CLAIM_ANALYSIS_NOT_CONFIGURED", retryable=False)
    return key


def _parse_json(content: str) -> dict:
    if not isinstance(content, str) or len(content) > 20000:
        raise ValueError("Invalid model response")
    text = content.strip()
    if text.startswith("```"):
        match = re.fullmatch(r"```(?:json)?\s*\n?(.*?)\s*```", text, re.DOTALL)
        if match is None:
            raise ValueError("Invalid JSON wrapper")
        text = match.group(1)
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


async def run_model(client: httpx.AsyncClient, model: str,
                    prepared_text: PreparedText, prompt_type: str) -> dict:
    prompt = {"CLASSIFICATION": CLASSIFICATION_PROMPT,
              "EXTRACTION": EXTRACTION_PROMPT}[prompt_type]
    # Cloud does not guarantee structured outputs. Ask for JSON and validate
    # locally instead of relying on the provider's `format` parameter.
    async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
        response = await client.post("/api/chat", json={
            "model": model, "stream": False,
            "think": "low" if model.startswith("gpt-oss") else False,
            "options": {"temperature": 0, "num_predict": 1024},
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps({
                    "submitted_text": prepared_text.normalised_text,
                    "language": prepared_text.language,
                }, ensure_ascii=False)},
            ],
        })
        response.raise_for_status()
        body = response.json()
        if body.get("done") is not True or body.get("done_reason") == "length":
            raise ValueError("Incomplete model response")
        value = _parse_json(body["message"]["content"])
        schema = ClassificationResponse if prompt_type == "CLASSIFICATION" else ExtractionResponse
        return schema.model_validate(value).model_dump()


def select_majority_result(results: dict[str, dict]) -> dict:
    """Exclude failures and require at least two validated classifier responses.

    claim_confidence means winning votes / all three configured models. It is
    an agreement indicator, not a calibrated probability of correct analysis.
    """
    valid = {}
    for model in CLASSIFICATION_MODELS:
        if model in results:
            try:
                valid[model] = ClassificationResponse.model_validate(results[model])
            except (ValidationError, TypeError):
                pass
    if len(valid) < 2:
        raise _error("Claim analysis could not obtain enough valid model responses. Please retry.",
                     "CLAIM_ANALYSIS_UNAVAILABLE")
    category, votes = Counter(item.claim_category for item in valid.values()).most_common(1)[0]
    if votes < 2:
        return {
            "extracted_claim": None, "claim_category": "unverifiable",
            "checkable": False, "claim_confidence": 0.0,
            "classification_reason": "The available models disagreed; a checkable claim could not be identified reliably.",
        }
    selected = next(item for item in valid.values() if item.claim_category == category)
    reason = selected.classification_reason
    if len(valid) < len(CLASSIFICATION_MODELS):
        reason += " One classifier was unavailable or returned an invalid response."
    return {
        **selected.model_dump(), "classification_reason": reason,
        "extracted_claim": None, "checkable": False,
        "claim_confidence": round(votes / len(CLASSIFICATION_MODELS), 2),
    }


def _grounded_claim(raw: dict, prepared: PreparedText) -> str:
    claim = ExtractionResponse.model_validate(raw).extracted_claim
    if claim.casefold() in {"null", "none", "n/a"}:
        raise ValueError("No claim extracted")
    # Require a source span, allowing whitespace/capitalisation changes. This
    # rejects invented wording but cannot prove that all qualifiers were kept.
    def normalise(text):
        return " ".join(text.split()).casefold().rstrip(".!?")
    normalised_claim = normalise(claim)
    if not re.search(r"\w", normalised_claim) or normalised_claim not in normalise(prepared.normalised_text):
        raise ValueError("Extracted claim is not present in the submitted text")
    return claim


async def _analyse_with_client(prepared: PreparedText, client: httpx.AsyncClient) -> ClaimAnalysis:
    outputs = await asyncio.gather(*(
        run_model(client, model, prepared, "CLASSIFICATION")
        for model in CLASSIFICATION_MODELS
    ), return_exceptions=True)
    results = {model: output for model, output in zip(CLASSIFICATION_MODELS, outputs)
               if isinstance(output, dict)}
    final = select_majority_result(results)
    if final["claim_category"] == "factual":
        try:
            output = await run_model(client, EXTRACTION_MODEL, prepared, "EXTRACTION")
            final["extracted_claim"] = _grounded_claim(output, prepared)
            final["checkable"] = True
        except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError, AttributeError):
            raise _error("A factual claim could not be extracted reliably. Please retry.",
                         "CLAIM_EXTRACTION_FAILED") from None
    return ClaimAnalysis.model_validate(final)


async def _analyse(prepared: PreparedText, api_key: str) -> ClaimAnalysis:
    try:
        async with asyncio.timeout(TOTAL_TIMEOUT_SECONDS):
            async with httpx.AsyncClient(
                base_url="https://ollama.com",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS, connect=10.0),
            ) as client:
                return await _analyse_with_client(prepared, client)
    except TimeoutError:
        raise _error("Claim analysis timed out. Please retry.",
                     "CLAIM_ANALYSIS_TIMEOUT") from None


def analyse_claim(prepared_text: PreparedText) -> ClaimAnalysis:
    """Synchronous public entry point used by FastAPI's synchronous route."""
    return asyncio.run(_analyse(prepared_text, _api_key()))
