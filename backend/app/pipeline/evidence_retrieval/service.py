"""Google fact-check discovery with Tavily source extraction and search fallback."""

import asyncio
from collections.abc import Callable, Mapping
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
import math
from functools import partial
import os
from pathlib import Path
import re
from typing import Any

from dotenv import load_dotenv
import httpx

from app.pipeline.shared.models import ClaimAnalysis, EvidenceCandidate, RetrievalResult
from app.pipeline.shared.errors import PipelineComponentError
from app.pipeline.shared.dates import dated_search_claim
from . import providers
from .query_planning import format_search_amounts, plan_queries
from .sources import SourceNotAllowed, canonical_url, source_details


EvidenceSearch = Callable[[str], list[dict[str, Any]]]
PROJECT_ENV = Path(__file__).resolve().parents[4] / ".env"
MIN_RETRIEVAL_SCORE = 0.60
TOTAL_TIMEOUT_SECONDS = 65.0
MAX_EVIDENCE = 6
RETRIEVAL_VERSION = "retrieval-v2"
STOP_WORDS = set("a an and are as at be been being by for from had has have in is it of on or that the this to was were will with would i me my we us our need needs".split())
PROVIDER_ERRORS = (httpx.HTTPError, TimeoutError, ValueError, TypeError, KeyError)


def _tokens(text: str) -> set[str]:
    # Thousands separators are formatting, not different amounts. Preserve
    # the claim itself; this normalisation is only for retrieval matching.
    text = re.sub(r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b",
                  lambda match: match.group(0).replace(",", ""), text)
    return set(re.findall(r"[a-z0-9]+", text.casefold())) - STOP_WORDS


def relevance(claim: str, passage: str) -> float:
    words = _tokens(claim)
    return len(words & _tokens(passage)) / len(words) if words else 0.0


def select_passage(claim: str, text: str, review_rating: str | None = None) -> str:
    """Keep a contiguous group of source sentences including nearby context.

    This lexical window is not a semantic verifier. Never use a generated answer
    or Google's repeated reviewed-claim text in place of a source passage.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Missing source passage")
    text = re.sub(r"\s+", " ", text[:100000]).strip()
    if isinstance(review_rating, str) and review_rating.strip():
        # Prefer the publisher's claim-and-verdict block when both Google and
        # the extracted page identify that rating. Do not manufacture a verdict
        # from metadata or return a headline that merely repeats the rumour.
        match = re.search(r"\b(?:rating|verdict)\s*:\s*" + re.escape(review_rating.strip()) + r"\b", text, re.I)
        if match:
            labels = list(re.finditer(r"\bclaim\s*:", text[:match.start()], re.I))
            start = labels[-1].start() if labels and match.start() - labels[-1].start() < 900 else max(0, match.start() - 300)
            return text[start:start + 1800]
    sentences = re.split(r"(?<=[.!?])\s+", text)
    index = max(range(len(sentences)), key=lambda i: relevance(claim, sentences[i]))
    # A bounded context window keeps adjacent qualifications and rebuttals.
    passage = " ".join(sentences[max(0, index - 1):index + 3])
    if len(passage) > 1800:
        # Avoid taking a navigation-heavy prefix of a huge unsplit page.
        words = list(re.finditer(r"\S+", passage))
        windows = [passage[words[i].start():words[min(i + 219, len(words) - 1)].end()]
                   for i in range(0, len(words), 100)]
        passage = max(windows, key=lambda value: relevance(claim, value))[:1800]
    return passage


def _date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        try:
            return parsedate_to_datetime(value).date()
        except (ValueError, TypeError, OverflowError):
            return None


def _candidate(claim: str, *, url: str, title: str, content: str,
               score: float | None = None, published_at=None, fact_check=False,
               review_rating: str | None = None) -> EvidenceCandidate | None:
    clean_url = canonical_url(url)
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Missing citation title")
    passage = select_passage(claim, content, review_rating)
    overlap = relevance(claim, passage)
    if score is None:
        score = overlap
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1:
        raise ValueError("Invalid relevance score")
    # Provider ranking is only relevance, never truth. Require actual passage
    # overlap as well so a high provider score cannot rescue unrelated content.
    score = min(score, overlap)
    if score < MIN_RETRIEVAL_SCORE:
        return None
    publisher, source_type = source_details(clean_url)
    return EvidenceCandidate(
        evidence_id="source-" + sha256(clean_url.encode()).hexdigest()[:16],
        title=title.strip(), url=clean_url, publisher=publisher,
        published_at=_date(published_at), passage=passage,
        source_type="fact_check" if fact_check else source_type,
        retrieval_score=round(score, 4), retrieved_at=datetime.now(timezone.utc))


def _deduplicate(items: list[EvidenceCandidate]) -> list[EvidenceCandidate]:
    urls, passages, identifiers = set(), set(), set()
    kept = []
    for item in sorted(items, key=lambda item: item.retrieval_score, reverse=True):
        # Preserve meaningful query parameters but collapse http/https variants.
        url = re.sub(r"^https?://", "", str(item.url)).rstrip("/")
        passage = " ".join(item.passage.casefold().split())
        if url in urls or passage in passages or item.evidence_id in identifiers:
            continue
        urls.add(url)
        passages.add(passage)
        identifiers.add(item.evidence_id)
        kept.append(item)
    return kept[:MAX_EVIDENCE]


def _finish(items: list[EvidenceCandidate], warnings: list[str], failed: bool) -> RetrievalResult:
    evidence = _deduplicate(items)
    if evidence:
        return RetrievalResult(retrieval_status="completed", evidence=evidence, warnings=warnings)
    if failed:
        return RetrievalResult(retrieval_status="failed", warnings=warnings or ["Evidence search is unavailable."])
    return RetrievalResult(retrieval_status="no_evidence", warnings=warnings + ["No sufficiently relevant evidence was found."])


async def _retrieve_with_client(claim: str, client: httpx.AsyncClient,
                                google_key: str, tavily_key: str,
                                planning_key: str | None = None) -> RetrievalResult:
    query = format_search_amounts(" ".join(claim.split()))[:400]
    warnings, evidence = [], []
    failed = False
    reviews = {}
    try:
        claims = await providers.google_search(client, query, google_key)
        for item in claims:
            if not isinstance(item.get("text"), str) or not isinstance(item.get("claimReview", []), list):
                raise ValueError("Invalid reviewed claim")
            if relevance(claim, item["text"]) < MIN_RETRIEVAL_SCORE:
                continue
            for review in item.get("claimReview", []):
                if not isinstance(review, dict):
                    raise ValueError("Invalid review")
                language = review.get("languageCode", "en")
                if not isinstance(language, str):
                    raise ValueError("Invalid review language")
                if language.split("-")[0] != "en":
                    continue
                try:
                    url = canonical_url(review.get("url"))
                except SourceNotAllowed:
                    continue
                reviews.setdefault(url, review)
        reviews = dict(list(reviews.items())[:3])
    except PROVIDER_ERRORS:
        failed = True
        warnings.append("Google Fact Check was unavailable or returned an invalid response; tried Tavily search.")

    if reviews:
        try:
            extracted = await providers.tavily_extract(client, list(reviews), tavily_key)
            seen = set()
            for item in extracted["results"]:
                if not isinstance(item, dict):
                    raise ValueError("Invalid extracted page")
                url = canonical_url(item.get("url"))
                if url not in reviews:
                    continue  # Never attach another page's metadata to this text.
                review = reviews[url]
                candidate = _candidate(claim, url=url, title=review.get("title"),
                    content=item.get("raw_content"), published_at=review.get("reviewDate"), fact_check=True,
                    review_rating=review.get("textualRating"))
                seen.add(url)
                if candidate:
                    evidence.append(candidate)
            if set(reviews) - seen or extracted.get("failed_results"):
                failed = True
                warnings.append("Some fact-check pages could not be extracted; tried additional search.")
        except PROVIDER_ERRORS:
            failed = True
            warnings.append("Fact-check source extraction failed; tried Tavily search.")

    if len(_deduplicate(evidence)) < 2:
        try:
            results = await providers.tavily_search(client, query, tavily_key)
            invalid = 0
            for item in results:
                try:
                    canonical_url(item.get("url"))
                except SourceNotAllowed:
                    continue  # Enforce catalogue even if the provider ignores it.
                except ValueError:
                    invalid += 1
                    continue
                try:
                    if "score" not in item or item["score"] is None:
                        raise ValueError("Missing provider relevance score")
                    candidate = _candidate(claim, url=item["url"], title=item.get("title"),
                        content=item.get("content"), score=item.get("score"),
                        published_at=item.get("published_date"))
                    if candidate:
                        evidence.append(candidate)
                except (ValueError, TypeError):
                    invalid += 1
            if invalid:
                failed = True
                warnings.append("Some search results had invalid citation or passage data and were discarded.")
        except PROVIDER_ERRORS:
            failed = True
            warnings.append("Tavily evidence search was unavailable or returned an invalid response.")

    # Natural wording can retrieve only forums or other out-of-scope pages.
    # Try bounded policy/topic formulations before concluding there is no evidence.
    # Keep both the approved source filter and ORIGINAL claim for passage ranking.
    if not evidence and not failed and planning_key:
        try:
            queries = await plan_queries(client, claim, planning_key)
            for expanded_query in queries:
                results = await providers.tavily_search(client, expanded_query, tavily_key)
                for item in results:
                    try:
                        canonical_url(item.get("url"))
                        if item.get("score") is None:
                            raise ValueError("Missing provider relevance score")
                        candidate = _candidate(claim, url=item.get("url"), title=item.get("title"),
                            content=item.get("content"), score=item.get("score"),
                            published_at=item.get("published_date"))
                        if candidate:
                            evidence.append(candidate)
                    except SourceNotAllowed:
                        continue
                    except (ValueError, TypeError):
                        failed = True
                        warnings.append("Some additional search results had invalid source data and were discarded.")
                if evidence:
                    break
        except PROVIDER_ERRORS:
            failed = True
            warnings.append("Additional evidence search could not be completed.")
    return _finish(evidence, warnings, failed)


async def _live(claim: str, google_key: str, tavily_key: str) -> RetrievalResult:
    try:
        async with asyncio.timeout(TOTAL_TIMEOUT_SECONDS):
            async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0), follow_redirects=False) as client:
                return await _retrieve_with_client(claim, client, google_key, tavily_key,
                    planning_key=os.environ.get("OLLAMA_API_KEY", "").strip() or None)
    except TimeoutError:
        return RetrievalResult(retrieval_status="failed", warnings=["Evidence retrieval exceeded its time limit."])


def _injected(claim: str, search_func: EvidenceSearch) -> RetrievalResult:
    """Keep Chu's dictionary-based fake-search hook for existing team tests."""
    try:
        results = search_func(claim)
        if not isinstance(results, list):
            raise ValueError("Invalid search result")
        evidence = [EvidenceCandidate.model_validate(item) for item in results]
        return _finish([item for item in evidence if item.retrieval_score >= MIN_RETRIEVAL_SCORE], [], False)
    except TimeoutError:
        return RetrievalResult(retrieval_status="failed", warnings=[
            "Evidence search could not be completed because the search service timed out."])
    except Exception:
        # Do not expose provider exception strings, URLs or keys to the API.
        return RetrievalResult(retrieval_status="failed", warnings=["Evidence search could not be completed."])


def retrieve_evidence(claim_analysis: ClaimAnalysis | Mapping[str, Any],
                      search_func: EvidenceSearch | None = None, *, mode: str | None = None) -> RetrievalResult | dict[str, Any]:
    """Typed production handoff; dictionary callers retain Chu's JSON interface."""
    typed = isinstance(claim_analysis, ClaimAnalysis)
    claim = ClaimAnalysis.model_validate(claim_analysis)
    if not claim.checkable:
        result = RetrievalResult(retrieval_status="no_evidence", warnings=[
            "The claim is not checkable, so evidence retrieval was skipped."])
    elif search_func is not None:
        result = _injected(dated_search_claim(claim.extracted_claim, claim.date_context), search_func)
    else:
        load_dotenv(PROJECT_ENV, override=False)
        selected_mode = retrieval_mode() if mode is None else mode
        if selected_mode not in {"catalogue", "web"}:
            raise ValueError("Invalid retrieval mode")
        google_key = os.environ.get("GOOGLE_FACT_CHECK_API_KEY", "").strip()
        tavily_key = os.environ.get("TAVILY_API_KEY", "").strip()
        if not google_key or not tavily_key:
            result = RetrievalResult(retrieval_status="failed", warnings=[
                "Evidence retrieval requires GOOGLE_FACT_CHECK_API_KEY and TAVILY_API_KEY on the backend."])
        else:
            if selected_mode == "web":
                from .enhanced import live
                key = os.environ.get("OLLAMA_API_KEY", "").strip()
                result = (asyncio.run(live(claim.extracted_claim, google_key, tavily_key, key, date_context=claim.date_context)) if key
                    else RetrievalResult(retrieval_status="failed", warnings=[
                        "Web retrieval requires OLLAMA_API_KEY for semantic relevance checks."]))
            else:
                result = asyncio.run(_live(dated_search_claim(claim.extracted_claim, claim.date_context), google_key, tavily_key))
    return result if typed else result.model_dump(mode="json")


def retrieval_mode():
    load_dotenv(PROJECT_ENV, override=False)
    mode = os.environ.get("EVIDENCE_RETRIEVAL_MODE", "catalogue").strip().lower()
    if mode not in {"catalogue", "web"}:
        raise PipelineComponentError("Invalid evidence retrieval mode.",
            error_code="RETRIEVAL_INVALID_CONFIG", stage="evidence_retrieval", retryable=False)
    return mode


def configured_retriever():
    mode = retrieval_mode()
    if mode == "web":
        from .enhanced import VERSION
        return partial(retrieve_evidence, mode=mode), VERSION
    return partial(retrieve_evidence, mode=mode), RETRIEVAL_VERSION
