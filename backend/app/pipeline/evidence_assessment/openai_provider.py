"""Small OpenAI Responses transport for the grounded-verifier experiment.

Provider output is still untrusted. The caller validates JSON, citations, and
evidence applicability using the same contracts as the Ollama verifier.
"""

from copy import deepcopy
from dataclasses import dataclass, field
import os
import re
from typing import Any

import httpx


DEFAULT_MODEL = "gpt-6.1-sol"


class OpenAIProviderError(Exception):
    """Only locally authored, safe diagnostics leave this transport."""

    def __init__(self, reason: str, code: str, message: str, *, retryable: bool):
        super().__init__(message)
        self.reason = reason
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True)
class OpenAISettings:
    api_key: str = field(repr=False)
    model: str = DEFAULT_MODEL
    reasoning_effort: str = "medium"
    max_output_tokens: int = 6000


@dataclass(frozen=True)
class OpenAIResponse:
    content: str
    usage: dict[str, int]


def get_settings() -> OpenAISettings:
    """Read credentials only when this provider is explicitly selected."""
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise OpenAIProviderError("missing_key", "OPENAI_NOT_CONFIGURED",
            "The OpenAI evidence assessment service is not configured.", retryable=False)
    model = os.environ.get("OPENAI_ASSESSMENT_MODEL", DEFAULT_MODEL).strip()
    effort = os.environ.get("OPENAI_REASONING_EFFORT", "medium").strip().lower()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}", model):
        raise OpenAIProviderError("invalid_model", "OPENAI_CONFIGURATION_INVALID",
            "The OpenAI assessment model setting is invalid.", retryable=False)
    if effort not in {"low", "medium", "high", "xhigh"}:
        raise OpenAIProviderError("invalid_effort", "OPENAI_CONFIGURATION_INVALID",
            "The OpenAI reasoning setting is invalid.", retryable=False)
    return OpenAISettings(api_key=key, model=model, reasoning_effort=effort)


def strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Adapt Pydantic's schema to the supported strict Structured Outputs form.

    Optional nullable fields retain their null union, and defaulted collections
    become required collections. Local validation remains authoritative for
    every bound and cross-field rule. The original schema is never modified.
    """
    original = deepcopy(schema)

    def invalid():
        # Schema values or paths must not escape through configuration errors.
        return OpenAIProviderError("invalid_schema", "OPENAI_SCHEMA_INVALID",
            "The OpenAI assessment response schema is not compatible.", retryable=False)

    def resolve(reference):
        if not isinstance(reference, str) or not (reference == "#" or reference.startswith("#/")):
            raise invalid()
        result = original
        for part in reference[2:].split("/") if reference != "#" else []:
            key = part.replace("~1", "/").replace("~0", "~")
            if not isinstance(result, dict) or key not in result:
                raise invalid()
            result = result[key]
        if not isinstance(result, dict):
            raise invalid()
        return deepcopy(result)

    def merge(base, extra):
        """Inline a reference without overwriting a stricter bound."""
        result = deepcopy(base)
        for key, value in extra.items():
            if key not in result or result[key] == value:
                result[key] = deepcopy(value)
            elif key in {"title", "description", "default", "examples", "deprecated"}:
                result[key] = deepcopy(value)
            elif key in {"minimum", "exclusiveMinimum", "minLength", "minItems", "minProperties"}:
                result[key] = max(result[key], value)
            elif key in {"maximum", "exclusiveMaximum", "maxLength", "maxItems", "maxProperties"}:
                result[key] = min(result[key], value)
            elif key == "required":
                result[key] = list(dict.fromkeys([*result[key], *value]))
            elif key == "enum":
                result[key] = [item for item in result[key] if item in value]
                if not result[key]:
                    raise invalid()
            else:
                # Arbitrary conflicting constraints need an intersection (allOf),
                # which strict outputs does not support. Fail rather than weaken.
                raise invalid()
        return result

    def expand(reference, expanding):
        if reference in expanding:
            raise invalid()
        node = resolve(reference)
        if "$ref" in node:
            inherited = expand(node["$ref"], (*expanding, reference))
            node = merge(inherited, {key: value for key, value in node.items() if key != "$ref"})
        return node

    def visit(node, expanding=()):
        if not isinstance(node, dict):
            return deepcopy(node)
        node = deepcopy(node)
        if "$ref" in node:
            reference = node["$ref"]
            resolve(reference)  # Even retained bare references must resolve locally.
            if len(node) > 1:
                node = merge(expand(reference, expanding),
                             {key: value for key, value in node.items() if key != "$ref"})
                expanding = (*expanding, reference)
        node.pop("default", None)
        properties = node.get("properties")
        if node.get("type") == "object" or isinstance(properties, dict):
            node["additionalProperties"] = False
            if isinstance(properties, dict):
                node["required"] = list(properties)
        # Visit schema locations only: field names and annotation dictionaries
        # are not schema keywords (a field could itself be named "default").
        for key in ("$defs", "definitions", "properties", "patternProperties"):
            if isinstance(node.get(key), dict):
                node[key] = {name: visit(value, expanding) for name, value in node[key].items()}
        for key in ("anyOf", "oneOf", "allOf", "prefixItems"):
            if isinstance(node.get(key), list):
                node[key] = [visit(value, expanding) for value in node[key]]
        for key in ("items", "additionalProperties", "not", "if", "then", "else"):
            if isinstance(node.get(key), dict):
                node[key] = visit(node[key], expanding)
        return node

    return visit(original)


def _invalid_response() -> OpenAIProviderError:
    return OpenAIProviderError("invalid_response", "OPENAI_INVALID_RESPONSE",
        "OpenAI returned an invalid assessment response. Please retry.", retryable=True)


def _safe_usage(body: dict[str, Any]) -> dict[str, int]:
    usage = body.get("usage")
    if not isinstance(usage, dict):
        return {}
    result = {key: usage[key] for key in ("input_tokens", "output_tokens", "total_tokens")
              if type(usage.get(key)) is int and usage[key] >= 0}
    for group, key, label in (
        ("input_tokens_details", "cached_tokens", "cached_input_tokens"),
        ("output_tokens_details", "reasoning_tokens", "reasoning_tokens"),
    ):
        detail = usage.get(group)
        value = detail.get(key) if isinstance(detail, dict) else None
        if type(value) is int and value >= 0:
            result[label] = value
    return result


def _read_response(body: Any) -> OpenAIResponse:
    if not isinstance(body, dict):
        raise _invalid_response()
    status = body.get("status")
    if status == "incomplete":
        raise OpenAIProviderError("incomplete", "OPENAI_RESPONSE_INCOMPLETE",
            "OpenAI could not finish the assessment response. Please retry.", retryable=True)
    if status != "completed" or body.get("error") is not None:
        raise _invalid_response()
    output = body.get("output")
    if not isinstance(output, list) or not output:
        raise _invalid_response()
    texts = []
    message_count = 0
    for item in output:
        if not isinstance(item, dict):
            raise _invalid_response()
        if item.get("type") == "reasoning":
            continue
        if (item.get("type") != "message" or item.get("role") != "assistant"
                or item.get("status") != "completed"):
            raise _invalid_response()
        message_count += 1
        content = item.get("content")
        if not isinstance(content, list) or not content:
            raise _invalid_response()
        for block in content:
            if not isinstance(block, dict):
                raise _invalid_response()
            if block.get("type") == "refusal":
                raise OpenAIProviderError("refusal", "OPENAI_ASSESSMENT_REFUSED",
                    "OpenAI could not assess this content.", retryable=False)
            if block.get("type") != "output_text" or not isinstance(block.get("text"), str):
                raise _invalid_response()
            texts.append(block["text"])
    if message_count != 1 or not texts or not "".join(texts).strip():
        raise _invalid_response()
    return OpenAIResponse(content="".join(texts).strip(), usage=_safe_usage(body))


async def request_assessment(client: httpx.AsyncClient, *, settings: OpenAISettings,
                             instructions: str, input_text: str,
                             schema: dict[str, Any]) -> OpenAIResponse:
    """One request; the caller owns the timeout, repair policy and total budget."""
    try:
        response = await client.post("/v1/responses",
            headers={"Authorization": f"Bearer {settings.api_key}"}, json={
                "model": settings.model,
                "store": False,
                "instructions": instructions,
                "input": [{"role": "user", "content": input_text}],
                "reasoning": {"effort": settings.reasoning_effort},
                "max_output_tokens": settings.max_output_tokens,
                "text": {"format": {"type": "json_schema", "name": "uiabo_verification",
                                     "strict": True, "schema": strict_schema(schema)}},
            })
    except httpx.TimeoutException:
        raise OpenAIProviderError("timeout", "OPENAI_ASSESSMENT_TIMEOUT",
            "OpenAI evidence assessment timed out. Please retry.", retryable=True) from None
    except httpx.HTTPError:
        raise OpenAIProviderError("network", "OPENAI_UNAVAILABLE",
            "OpenAI evidence assessment is temporarily unavailable. Please retry.", retryable=True) from None
    if response.status_code in {401, 403}:
        raise OpenAIProviderError("authentication", "OPENAI_ACCESS_DENIED",
            "The OpenAI assessment service could not authenticate or access this model.", retryable=False)
    if response.status_code == 429:
        raise OpenAIProviderError("rate_limited", "OPENAI_RATE_LIMITED",
            "OpenAI assessment capacity or API quota is unavailable. Please try again later.", retryable=True)
    if response.status_code >= 500:
        raise OpenAIProviderError("service_unavailable", "OPENAI_UNAVAILABLE",
            "OpenAI evidence assessment is temporarily unavailable. Please retry.", retryable=True)
    if response.status_code in {400, 404}:
        # Inspect only an allowlisted machine code. Never return provider text,
        # request identifiers, model names from errors, or the raw error body.
        try:
            payload = response.json()
            error = payload.get("error") if isinstance(payload, dict) else None
            code = error.get("code") if isinstance(error, dict) else None
        except ValueError:
            code = None
        if code == "invalid_json_schema":
            raise OpenAIProviderError("invalid_schema", "OPENAI_SCHEMA_INVALID",
                "OpenAI could not accept the assessment response schema. Check the backend configuration.", retryable=False)
        if code == "model_not_found":
            raise OpenAIProviderError("model_unavailable", "OPENAI_MODEL_UNAVAILABLE",
                "The configured OpenAI assessment model is unavailable to this API project.", retryable=False)
    if response.status_code != 200:
        raise OpenAIProviderError("request_rejected", "OPENAI_REQUEST_REJECTED",
            "OpenAI could not accept the assessment request. Check the backend model configuration.", retryable=False)
    try:
        body = response.json()
    except ValueError:
        raise _invalid_response() from None
    return _read_response(body)
