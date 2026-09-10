"""Opt-in web retrieval: discover broadly, extract originals, assess eligibility.

Bounded to three Tavily searches, one Google request, four extracted URLs and four
semantic relevance calls. A successful but inconclusive search is not an outage.
Partial validated evidence survives a later timeout with an explicit warning.
"""

import asyncio
from datetime import datetime, timezone
from hashlib import sha256
import math

import httpx
from pydantic import ValidationError

from app.pipeline.shared.models import EvidenceCandidate, EvidenceProvenance, RetrievalTrace
from . import providers
from .query_planning import format_search_amounts, plan_queries
from .relevance import select_with_client
from .service import _date, _deduplicate, _finish, relevance, PROVIDER_ERRORS
from .source_policy import classify_source, extractable_lead, original_links, public_url
from app.pipeline.shared.dates import dated_search_claim

VERSION = "retrieval-web-v6"
TOTAL_TIMEOUT_SECONDS = 65.0
MAX_PAGES = 4


def enough_evidence(items):
    return len({item.provenance.origin_group for item in _deduplicate(items)
        if item.provenance and item.provenance.relevance == "direct"
        and item.provenance.applicability == "established"}) >= 2


class RetrievalRun:
    def __init__(self, claim, client, google_key, tavily_key, ollama_key, *, date_context=None):
        self.claim, self.client = claim, client
        self.date_context = date_context
        self.search_claim = dated_search_claim(claim, date_context)
        self.google_key, self.tavily_key, self.ollama_key = google_key, tavily_key, ollama_key
        self.trace = RetrievalTrace()
        self.evidence, self.warnings = [], []
        self.pool, self.attempted = {}, set()
        self.failed = False
        self.unavailable_pages = set()
        self.reviewed_pages = 0
        self.now = datetime.now(timezone.utc)

    def event(self, decision, url="", **details):
        if len(self.trace.decisions) < 40:
            self.trace.decisions.append({"decision": decision, "url": url, **details})

    def failure(self, stage):
        self.failed = True
        message = f"Some {stage} could not be completed; any returned evidence was validated separately."
        if message not in self.warnings:
            self.warnings.append(message)

    def add(self, item, method):
        try:
            url = public_url(item.get("url"))
            title = item.get("title")
            score = item.get("score", 0.5)
            if (not isinstance(title, str) or not title.strip()
                    or isinstance(score, bool) or not isinstance(score, (int, float))
                    or not math.isfinite(score) or not 0 <= score <= 1):
                raise ValueError("Invalid candidate")
            # Merge metadata without allowing the same page extra budget.
            if url not in self.pool:
                self.pool[url] = {"url": url, "title": title[:500], "score": score,
                    "published_at": _date(item.get("published_date")), "method": method,
                    "content": item.get("content", "") if isinstance(item.get("content", ""), str) else ""}
                self.event("discovered_" + classify_source(url).policy, url)
            elif score > self.pool[url]["score"]:
                # A later neutral query can rank the actual policy page above
                # pages matching the rumour. Keep its improved discovery rank;
                # the URL still receives only one extraction budget slot.
                self.pool[url]["score"] = score
                if isinstance(item.get("content"), str):
                    self.pool[url]["content"] = item["content"]
        except (ValueError, TypeError):
            self.event("rejected_invalid_candidate")

    async def search(self, query, *, broad=False):
        self.trace.search_requests += 1
        self.event("web_search" if broad else "preferred_search", query=query)
        try:
            items = await providers.tavily_search(self.client, query, self.tavily_key, broad=broad)
            for item in items:
                self.add(item, "web_search" if broad else "preferred_search")
        except PROVIDER_ERRORS:
            self.failure("web searches")

    async def google(self, query):
        try:
            for item in await providers.google_search(self.client, query, self.google_key):
                reviews = item.get("claimReview", [])
                if not isinstance(reviews, list):
                    raise ValueError("Invalid reviews")
                for review in reviews[:3]:
                    if not isinstance(review, dict):
                        raise ValueError("Invalid review")
                    language = review.get("languageCode", "en")
                    if not isinstance(language, str) or language.split("-")[0] != "en":
                        continue
                    # Metadata is discovery only; the actual page must be extracted.
                    self.add({"url": review.get("url"), "title": review.get("title"),
                        "published_date": review.get("reviewDate"), "score": 0.8,
                        "content": item.get("text", "")}, "google_fact_check")
        except PROVIDER_ERRORS:
            self.failure("fact-check searches")

    def next_pages(self, limit, *, eligible_only=False):
        candidates = [item for url, item in self.pool.items() if url not in self.attempted
                      and (classify_source(url).eligible or (not eligible_only and extractable_lead(url)))]
        candidates.sort(key=lambda item: (classify_source(item["url"]).eligible,
            item["score"], relevance(self.claim, item["content"])), reverse=True)
        chosen, origins = [], set()
        # Source diversity before second pages from an already selected family.
        for item in candidates:
            origin = classify_source(item["url"]).origin_group
            if origin not in origins:
                chosen.append(item)
                origins.add(origin)
        chosen.extend(item for item in candidates if item not in chosen)
        return chosen[:limit]

    async def extract_pages(self, pages):
        if not pages:
            return
        urls = [item["url"] for item in pages]
        self.attempted.update(urls)
        self.trace.extraction_urls += len(urls)
        try:
            response = await providers.tavily_extract(self.client, urls, self.tavily_key, format="markdown")
        except PROVIDER_ERRORS:
            if any(classify_source(url).eligible for url in urls):
                self.failure("page extractions")
            else:
                self.event("optional_lead_extraction_failed")
            return
        seen, jobs = set(), []
        reported_unavailable = set()
        for failure in response.get("failed_results", []):
            try:
                url = public_url(failure.get("url"))
                if url not in urls:
                    raise ValueError("Unrequested failed extraction")
                reported_unavailable.add(url)
            except (ValueError, TypeError, AttributeError):
                self.failure("page extractions")
        for raw in response["results"]:
            try:
                url = public_url(raw.get("url"))
                if url not in urls or url in seen:
                    self.event("rejected_unrequested_or_duplicate_extraction", url)
                    self.failure("page extractions")
                    continue
                text = raw.get("raw_content")
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("Empty extracted page")
                seen.add(url)
                source = classify_source(url)
                if not source.eligible:
                    self.event("lead_only_unverified_publisher", url)
                    for linked in original_links(text):
                        if linked != url:
                            self.add({"url": linked, "title": "Linked original source",
                                      "score": 0.7}, "source_link")
                    continue
                jobs.append(self.select(self.pool[url], text, source))
            except (ValueError, TypeError, AttributeError):
                self.failure("page extractions")
        for url in set(urls) - seen:
            if not classify_source(url).eligible:
                continue
            if url not in reported_unavailable:
                self.failure("page extractions")
                continue
            # A provider can complete extraction while an individual website is
            # unavailable. Preserve that coverage gap without treating it as a
            # provider outage if other eligible pages were successfully reviewed.
            self.unavailable_pages.add(url)
            self.event("source_page_unavailable", url)
        if jobs:
            await asyncio.gather(*jobs)

    async def select(self, item, text, source):
        self.trace.relevance_calls += 1
        try:
            selection, passage = await select_with_client(self.client, self.claim, text,
                self.ollama_key, as_of=self.date_context.as_of if self.date_context else self.now.date(),
                published_at=item["published_at"], date_context=self.date_context)
            self.reviewed_pages += 1
            if selection.relevance == "irrelevant":
                self.event("rejected_semantically_irrelevant", item["url"])
                return
            self.evidence.append(EvidenceCandidate(
                evidence_id="source-" + sha256(item["url"].encode()).hexdigest()[:16],
                title=item["title"], url=item["url"], publisher=source.publisher,
                source_type=source.source_type, published_at=item["published_at"],
                retrieved_at=self.now, passage=passage,
                # Fixed ranking weights, NOT LLM confidence or truth probabilities.
                retrieval_score=0.9 if selection.relevance == "direct" else 0.5,
                provenance=EvidenceProvenance(source_policy=source.policy,
                    source_reason=source.reason, origin_group=source.origin_group,
                    discovery_method=item["method"], relevance=selection.relevance,
                    relevance_reason=selection.reason, relevance_quote=selection.quote,
                    applicability=selection.applicability,
                    applicability_reason=selection.applicability_reason,
                    condition_quotes=selection.condition_quotes)))
            self.event("accepted_" + selection.relevance + "_" + selection.applicability, item["url"])
        except PROVIDER_ERRORS as error:
            details = {}
            if isinstance(error, ValidationError):
                details["fields"] = ",".join(".".join(str(value) for value in item["loc"])
                    for item in error.errors(include_url=False, include_input=False))[:300]
            if isinstance(error, httpx.HTTPStatusError):
                details["http_status"] = str(error.response.status_code)
            self.event("relevance_failed_" + type(error).__name__, item["url"], **details)
            self.failure("semantic relevance checks")

    async def run(self):
        query = format_search_amounts(" ".join(self.search_claim.split()))[:400]
        try:
            async with asyncio.timeout(TOTAL_TIMEOUT_SECONDS):
                await asyncio.gather(self.google(query), self.search(query))
                await self.extract_pages(self.next_pages(2, eligible_only=True))
                if not enough_evidence(self.evidence):
                    # Use both alternative formulations when available. A planner
                    # failure still permits broad literal search.
                    async def expand():
                        try:
                            return await plan_queries(self.client, self.search_claim, self.ollama_key, allow_policy_lookup=True)
                        except PROVIDER_ERRORS:
                            self.failure("alternative query planning")
                            return []
                    alternatives = await expand()
                    await asyncio.gather(*(self.search(value, broad=True)
                                           for value in (alternatives[:2] or [query])))
                    # Leave room to follow an eligible original from an unknown page.
                    while len(self.attempted) < MAX_PAGES:
                        remaining = MAX_PAGES - len(self.attempted)
                        pages = self.next_pages(remaining)
                        if not pages:
                            break
                        if any(not classify_source(page["url"]).eligible for page in pages):
                            pages = pages[:1]
                        await self.extract_pages(pages)
                        if enough_evidence(self.evidence):
                            break
        except TimeoutError:
            self.failure("retrieval within its time limit")
        if any(event["decision"] == "lead_only_unverified_publisher" for event in self.trace.decisions):
            self.warnings.append("Some websites were used only as leads because their publisher identity was not established by the prototype source policy.")
        # Only exact copies are removed here. Near-identical text can contain
        # decisive negation/quantity changes; do not discard it on word overlap.
        if self.unavailable_pages:
            self.warnings.append("Some source pages could not be read, so evidence coverage is incomplete.")
        result = _finish(self.evidence, self.warnings,
            self.failed or bool(self.unavailable_pages and not self.reviewed_pages))
        result.trace = self.trace
        return result


async def retrieve_with_client(claim, client, google_key, tavily_key, ollama_key, *, date_context=None):
    return await RetrievalRun(claim, client, google_key, tavily_key, ollama_key, date_context=date_context).run()


async def live(claim, google_key, tavily_key, ollama_key, *, date_context=None):
    async with httpx.AsyncClient(timeout=httpx.Timeout(20, connect=5), follow_redirects=False) as client:
        return await retrieve_with_client(claim, client, google_key, tavily_key, ollama_key, date_context=date_context)
