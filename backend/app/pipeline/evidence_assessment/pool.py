"""pipeline-v3 whole-pool assessment: one call reads every source.

Provider chain is strictly Jev -> gpt-oss with an IDENTICAL input shape and an
IDENTICAL per-source output schema. There is no third mode and no per-slice
fan-out: if both providers fail, the pipeline fails retryably. Downstream
aggregation consumes the same AssessedEvidence contract as the semantic
assessor, so scoring, labels and persistence are unchanged.
"""

import asyncio
import json
import os
import re

from dotenv import load_dotenv
import httpx

from app.pipeline.shared.errors import PipelineComponentError
from app.pipeline.shared.models import (
    AssessedEvidence, ClaimAnalysis, RetrievalResult,
)
from . import forecast, policy
from .semantic import PROJECT_ENV, _error, baseline, future_scope_limitation
from .scoring import SCORING_VERSION

TOTAL_TIMEOUT_SECONDS = 65.0
PAGE_CAP_CHARS = 6000
MAX_POOL_SOURCES = 8
# Per-provider calibration for the settles gate. Jev's noul is an honest P(yes)
# (~0.45 for decisive pages); gpt-oss verbalizes all-or-nothing settles. The
# shape is identical; only the numeric operating point is provider-calibrated.
DEFAULT_SETTLES_JEV = 0.30
DEFAULT_SETTLES_OSS = 0.5
JEV_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
JEV_MODEL = "jev-latest"
OSS_MODEL = "gpt-oss:120b"

POOL_INSTRUCTIONS = """For EACH source s{i}, output one JSON object with:
verdict: one of supporting|contradicting|not_decisive|irrelevant (how this source bears on the claim)
confidence: 0-1
settles: 0-1 (does this source alone decisively settle the claim)
quality: 0-4 (0 irrelevant/unreliable, 4 primary authority)

Return only JSON: {{"sources": {{"s0": {{"verdict": "...", "confidence": 0.0, "settles": 0.0, "quality": 0.0}}, "s1": {{...}}, ...}}}}"""


def _stage_error(message: str, code: str) -> PipelineComponentError:
    return PipelineComponentError(message, error_code=code, stage="evidence_assessment",
                                  retryable=True)


def format_pool_state(claim_text: str, sources: list[tuple[str, str]]) -> str:
    """Identical state construction for every provider. Same shape, no matter what."""
    body = "\n\n".join(f"SOURCE {sid}:\n{text[:PAGE_CAP_CHARS]}" for sid, text in sources)
    return f"CLAIM: {claim_text}\n\n{body}"


def pool_questions(sids: list[str]) -> dict:
    """One Jev question per field per source; a single call fans out all of them."""
    questions = {}
    for sid in sids:
        questions[f"verdict_{sid}"] = {
            "type": "choice",
            "instructions": f"Based only on SOURCE {sid} in the state, how does it bear on the claim?",
            "criteria": {
                "supporting": f"SOURCE {sid} contains information establishing the claim is true",
                "contradicting": f"SOURCE {sid} contains information establishing the claim is false",
                "not_decisive": f"SOURCE {sid} is related but does not settle the claim either way",
                "irrelevant": f"SOURCE {sid} does not concern the claim's subject"}}
        questions[f"settles_{sid}"] = {
            "type": "noul",
            "instructions": f"Does SOURCE {sid} alone decisively settle the claim?"}
        questions[f"quality_{sid}"] = {
            "type": "score",
            "instructions": f"How relevant and authoritative is SOURCE {sid} for the claim?",
            "criteria": ["irrelevant to the claim", "marginally relevant",
                         "relevant but not decisive", "relevant and near-decisive",
                         "directly decisive"]}
    return questions


def _parse_sources(raw: dict) -> dict:
    """Validate the shared per-source schema used by every provider."""
    sources = raw.get("sources")
    if not isinstance(sources, dict) or not sources:
        raise ValueError("Missing sources object")
    parsed = {}
    for sid, entry in sources.items():
        if not isinstance(entry, dict):
            raise ValueError(f"Source {sid} is not an object")
        verdict = entry.get("verdict")
        if verdict not in ("supporting", "contradicting", "not_decisive", "irrelevant"):
            raise ValueError(f"Source {sid} has invalid verdict")
        parsed[sid] = {
            "verdict": verdict,
            "confidence": max(0.0, min(1.0, float(entry.get("confidence", 0) or 0))),
            "settles": max(0.0, min(1.0, float(entry.get("settles", 0) or 0))),
            "quality": max(0, min(4, int(float(entry.get("quality", 0) or 0)))),
        }
    return parsed


async def _call_jev(client: httpx.AsyncClient, key: str, state: str, sids: list[str]) -> dict:
    response = await client.post(JEV_ENDPOINT,
        headers={"Authorization": f"Bearer {key}"},
        json={"state": state[:200000], "model": JEV_MODEL,
              "questions": pool_questions(sids)})
    response.raise_for_status()
    answers = response.json()["answers"]
    out = {}
    for sid in sids:
        verdict = answers[f"verdict_{sid}"]
        choice = verdict.get("choice")
        if choice not in ("supporting", "contradicting", "not_decisive", "irrelevant"):
            raise ValueError(f"Jev returned invalid verdict for {sid}")
        probabilities = verdict.get("probabilities") or {}
        raw_confidence = verdict.get("confidence")
        settles = answers[f"settles_{sid}"].get("noul")
        quality = answers[f"quality_{sid}"].get("score")
        out[sid] = {
            "verdict": choice,
            "confidence": max(0.0, min(1.0, float(raw_confidence)
                               if raw_confidence is not None
                               else float(probabilities.get(choice, 0) or 0))),
            "settles": max(0.0, min(1.0, float(settles if settles is not None else 0))),
            "quality": max(0, min(4, int(float(quality if quality is not None else 0)))),
        }
    return out


async def _call_oss(client: httpx.AsyncClient, key: str, state: str) -> dict:
    response = await client.post("/api/chat", json={
        "model": OSS_MODEL, "stream": False, "think": "medium",
        "options": {"temperature": 0, "num_predict": 4096},
        "messages": [{"role": "user", "content":
                      state + "\n\n" + POOL_INSTRUCTIONS.format(i=0)}]})
    response.raise_for_status()
    body = response.json()
    if body.get("done") is not True or body.get("done_reason") == "length":
        raise ValueError("Incomplete model response")
    content = body["message"]["content"]
    match = re.search(r"\{.*\}", content, re.S)
    if not match:
        raise ValueError("No JSON in response")
    return _parse_sources(json.loads(match.group(0)))


def _provider_keys() -> tuple[str | None, str | None]:
    load_dotenv(PROJECT_ENV, override=False)
    jev = os.environ.get("JEV_API_KEY", "").strip() or None
    oss = os.environ.get("OLLAMA_API_KEY", "").strip() or None
    return jev, oss


async def _pool_verdicts(claim_text: str, sources: list[tuple[str, str]]) -> tuple[dict, str]:
    """Jev -> gpt-oss, same state, same schema. Both fail => retryable error."""
    state = format_pool_state(claim_text, sources)
    sids = [sid for sid, _ in sources]
    errors: list[str] = []
    jev_key, oss_key = _provider_keys()
    if jev_key:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=10.0)) as client:
                return await _call_jev(client, jev_key, state, sids), "jev"
        except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError) as error:
            errors.append(f"jev:{type(error).__name__}")
    if oss_key:
        try:
            async with httpx.AsyncClient(
                base_url="https://ollama.com",
                headers={"Authorization": f"Bearer {oss_key}"},
                timeout=httpx.Timeout(45.0, connect=10.0)) as client:
                return await _call_oss(client, oss_key, state), "oss"
        except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError) as error:
            errors.append(f"oss:{type(error).__name__}")
    raise _stage_error(
        "Evidence could not be assessed reliably. Please retry.",
        "ASSESSMENT_UNAVAILABLE") from (
        errors[-1] if errors else None)


def settles_threshold(provider: str | None = None) -> float:
    load_dotenv(PROJECT_ENV, override=False)
    specific = {"jev": ("POOL_SETTLES_THRESHOLD_JEV", DEFAULT_SETTLES_JEV),
                "oss": ("POOL_SETTLES_THRESHOLD_OSS", DEFAULT_SETTLES_OSS)}
    env_name, default = (specific.get(provider or "", ("POOL_SETTLES_THRESHOLD",
                                                        DEFAULT_SETTLES_OSS)))
    raw = os.environ.get(env_name, "").strip()
    try:
        value = float(raw) if raw else default
    except ValueError:
        value = default
    return min(1.0, max(0.0, value))


def to_assessed(retrieval: RetrievalResult, verdicts: dict,
                threshold: float) -> list[AssessedEvidence]:
    """Map the shared per-source schema onto the existing assessment contract.

    quality_score uses prod's structural rule (source cap x retrieval relevance);
    the model's 0-4 quality is metadata for evidence cards, not a gate input.
    """
    assessed = []
    for index, item in enumerate(retrieval.evidence):
        sid = f"s{index}"
        verdict = verdicts.get(sid) or {"verdict": "not_decisive", "settles": 0.0,
                                        "quality": 0, "confidence": 0.0}
        stance = ("supporting" if verdict["verdict"] == "supporting"
                  else "contradicting" if verdict["verdict"] == "contradicting" else "neutral")
        if stance != "neutral" and float(verdict["settles"]) < threshold:
            stance = "neutral"
        quality = baseline.calculate_quality_score(item, stance)
        reason = (f"Whole-pool assessment: {verdict['verdict']} "
                  f"(decisiveness {verdict['settles']:.2f}, quality {verdict['quality']}/4).")
        assessed.append(AssessedEvidence(
            evidence_id=item.evidence_id, stance=stance, quality_score=quality,
            assessment_reason=reason))
    return assessed


def _finish_aggregation(claim: ClaimAnalysis, retrieval: RetrievalResult,
                        assessed: list[AssessedEvidence], provider: str = "pool"):
    """Baseline scoring plus semantic.aggregate's uncertainty and explanation rules."""
    result = baseline.summarise_assessments(claim.extracted_claim or "", retrieval, assessed)
    result.scoring.version = SCORING_VERSION
    result.scoring.reasons.append(f"Assessed as one pool by the {provider} judge.")
    assessed = result.assessed_evidence
    if result.uncertainty == "Low":
        result.uncertainty = "Medium"
        result.uncertainty_reasons = [
            "The passages agree, but source independence and assessment accuracy have not been established."]
    result.uncertainty_reasons.append(
        "The risk indicator uses prototype rules; it is not a probability that the claim is false.")
    by_id = {item.evidence_id: item for item in retrieval.evidence}
    decisive = [item for item in assessed if item.stance != "neutral"]
    if decisive:
        chosen = [next(item for item in decisive if item.stance == stance)
                  for stance in ("supporting", "contradicting")
                  if any(item.stance == stance for item in decisive)]
        result.explanation += " " + " ".join(
            f"{by_id[item.evidence_id].publisher}: {item.assessment_reason}"
            for item in chosen)
    elif assessed:
        result.explanation = (
            "Related evidence was found, but it does not establish this claim. "
            + assessed[0].assessment_reason)
    if forecast.is_weather(claim):
        return forecast.attach_web_context(claim, result)
    return policy.summarise_policy(result, claim.extracted_claim or "", retrieval, [],
                                   claim.date_context)


def _pool_sources(items) -> list[tuple[str, str]]:
    """Whole-pool text per source; falls back to the selected passage."""
    sources = []
    for index, item in enumerate(items):
        text = (item.full_text or item.passage or "").strip()
        if text:
            sources.append((f"s{index}", text[:PAGE_CAP_CHARS]))
    return sources


async def _assess_async(claim: ClaimAnalysis, retrieval: RetrievalResult):
    if not claim.checkable or retrieval.retrieval_status != "completed":
        return baseline.assess_evidence(claim, retrieval)
    if len(retrieval.evidence) > MAX_POOL_SOURCES:
        raise _error("ASSESSMENT_INPUT_TOO_LARGE", "Too many evidence passages to assess.",
                     retryable=False)
    structured = forecast.assess_structured(claim, retrieval)
    web_sources = [item for item in retrieval.evidence if item.forecast is None]
    if structured is not None and not web_sources:
        return structured
    try:
        async with asyncio.timeout(TOTAL_TIMEOUT_SECONDS):
            if structured is not None:
                # Weather: structured official forecast plus pool-read web context.
                sub = RetrievalResult(retrieval_status="completed", evidence=web_sources)
                sources = _pool_sources(web_sources)
                verdicts, provider = await _pool_verdicts(claim.extracted_claim or "", sources)
                assessed = to_assessed(sub, verdicts, settles_threshold(provider))
                return forecast.merge_web_assessments(claim, retrieval, structured, assessed, [])
            sources = _pool_sources(retrieval.evidence)
            if not sources:
                return baseline.assess_evidence(claim, retrieval)
            verdicts, provider = await _pool_verdicts(claim.extracted_claim or "", sources)
            assessed = to_assessed(retrieval, verdicts, settles_threshold(provider))
            return _finish_aggregation(claim, retrieval, assessed, provider)
    except TimeoutError:
        raise _error("ASSESSMENT_TIMEOUT", "Evidence assessment timed out. Please retry.") from None


def assess_pool_evidence(claim: ClaimAnalysis, retrieval: RetrievalResult):
    """Synchronous entry point; drop-in for the semantic assessor."""
    return asyncio.run(_assess_async(claim, retrieval))


def configured_pool_assessor():
    """Factory like semantic.configured_assessor; loads no credentials on import."""
    load_dotenv(PROJECT_ENV, override=False)
    version = (f"pipeline-v3-pool:t{settles_threshold('jev'):.2f}/"
               f"{settles_threshold('oss'):.2f}:{SCORING_VERSION}")
    return assess_pool_evidence, version