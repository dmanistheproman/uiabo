"""Opt-in web retrieval: discover broadly, extract originals, assess eligibility.

Bounded to three Tavily searches, one Google request and four semantic relevance
calls. Four extraction slots allow up to two replacements for unavailable pages.
A successful but inconclusive search is not an outage.
Partial validated evidence survives a later timeout with an explicit warning.
"""

import asyncio
from datetime import datetime, timezone
from hashlib import sha256
import math

import httpx
from pydantic import ValidationError

from app.pipeline.shared.models import EvidenceCandidate, EvidenceProvenance, RetrievalTrace
from . import providers, official_forecast, official_climate
from .coverage import missing_coverage, requires_weather_context_search, weather_queries, weather_page_priority
from .query_planning import format_search_amounts, plan_queries
from .passport_entry import current_entry_query, entry_page_priority
from .relevance import select_with_client
from .service import _date, _deduplicate, _finish, relevance, PROVIDER_ERRORS
from .source_policy import classify_source, extractable_lead, original_links, public_url, url_identity, preferred_corporate_domains
from app.pipeline.shared.dates import dated_search_claim
from app.pipeline.shared.interpretation import relationship_queries, relationship_page_priority
from app.pipeline.shared.rankings import ranking_queries, ranking_page_priority, political_salary_ranking
from app.pipeline.shared.components import component_queries, component_discovery_anchor, component_page_priority, cpf_retirement_context
from .sources import SOURCES

VERSION = "retrieval-web-v16"
TOTAL_TIMEOUT_SECONDS = 65.0
MAX_PAGES = 4
MAX_REPLACEMENT_PAGES = 2


def enough_evidence(items):
    return len({item.provenance.origin_group for item in _deduplicate(items)
        if item.provenance and item.provenance.relevance == "direct"
        and item.provenance.applicability == "established"}) >= 2


class RetrievalRun:
    def __init__(self, claim, client, google_key, tavily_key, ollama_key, *, date_context=None, claim_context=None):
        self.claim, self.client = claim, client
        self.date_context = date_context
        self.claim_context = claim_context
        self.component_queries = component_queries(claim)
        self.component_pages_attempted = set()
        self.search_claim = dated_search_claim(claim, date_context)
        self.google_key, self.tavily_key, self.ollama_key = google_key, tavily_key, ollama_key
        self.trace = RetrievalTrace()
        self.evidence, self.warnings = [], []
        self.pool, self.attempted = {}, set()
        self.failed = False
        self.unavailable_pages = set()
        self.reviewed_pages = 0
        self.now = claim_context.assessed_at if claim_context else datetime.now(timezone.utc)

    def event(self, decision, url="", **details):
        if len(self.trace.decisions) < 40:
            self.trace.decisions.append({"decision": decision, "url": url, **details})

    def source(self, url):
        return classify_source(url, self.claim)

    def failure(self, stage):
        self.failed = True
        message = f"Some {stage} could not be completed; any returned evidence was validated separately."
        if message not in self.warnings:
            self.warnings.append(message)

    def add(self, item, method, *, component_id=None):
        try:
            url = public_url(item.get("url"))
            identity = url_identity(url)
            title = item.get("title")
            score = item.get("score", 0.5)
            if (not isinstance(title, str) or not title.strip()
                    or isinstance(score, bool) or not isinstance(score, (int, float))
                    or not math.isfinite(score) or not 0 <= score <= 1):
                raise ValueError("Invalid candidate")
            # Merge metadata without allowing the same page extra budget.
            if identity not in self.pool:
                self.pool[identity] = {"url": url, "title": title[:500], "score": score,
                    "published_at": _date(item.get("published_date")), "method": method,
                    "component_ids": {component_id} if component_id else set(),
                    "content": item.get("content", "") if isinstance(item.get("content", ""), str) else ""}
                self.event("discovered_" + self.source(url).policy, url)
            elif score > self.pool[identity]["score"]:
                # A later neutral query can rank the actual policy page above
                # pages matching the rumour. Keep its improved discovery rank;
                # the URL still receives only one extraction budget slot.
                self.pool[identity]["score"] = score
                if isinstance(item.get("content"), str):
                    self.pool[identity]["content"] = item["content"]
            if component_id:
                self.pool[identity]["component_ids"].add(component_id)
        except (ValueError, TypeError):
            self.event("rejected_invalid_candidate")

    async def search(self, query, *, broad=False):
        self.trace.search_requests += 1
        self.event("web_search" if broad else "preferred_search", query=query)
        try:
            domains = preferred_corporate_domains(self.claim) if not broad else None
            if not broad and political_salary_ranking(self.claim):
                domains = [*SOURCES, "politicalsalaries.com"]
            options = {"preferred_domains": domains} if domains else {}
            items = await providers.tavily_search(self.client, query, self.tavily_key, broad=broad, **options)
            component_id = ("event", "premise")[self.component_queries.index(query)] if query in self.component_queries else None
            for item in items:
                self.add(item, "web_search" if broad else "preferred_search", component_id=component_id)
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
        unavailable_origins = {self.source(url).origin_group for url in self.unavailable_pages}
        def tier_of(item):
            return (self.source(item["url"]).eligible,
                    self.source(item["url"]).origin_group not in unavailable_origins,
                    component_page_priority(self.claim, item["title"], item["url"], item["content"], as_of=self.now.date()),
                    relationship_page_priority(self.claim, item["title"], item["url"], item["content"]),
                    ranking_page_priority(self.claim, item["title"], item["url"], item["content"]))
        candidates = [item for url, item in self.pool.items() if url not in self.attempted
                      and (self.source(url).eligible or (not eligible_only and extractable_lead(url)))]
        candidates.sort(key=lambda item: (*tier_of(item),
            weather_page_priority(self.claim_context, item["title"], item["url"]),
            entry_page_priority(self.claim, item["title"], item["url"]),
            item["score"], relevance(self.claim, item["content"])), reverse=True)
        chosen, origins = [], set()
        # Reserve a discovery attempt for each material part, particularly the
        # premise that a literal event-led search can miss. Query membership is
        # only a scheduling hint: semantic selection still decides usefulness.
        for component_id in ("premise", "event") if self.component_queries else ():
            if component_id in self.component_pages_attempted:
                continue
            page = next((item for item in candidates if item not in chosen
                         and self.source(item["url"]).eligible
                         and (not cpf_retirement_context(self.claim)
                              or component_page_priority(self.claim, item["title"], item["url"], item["content"], as_of=self.now.date()) > 0)
                         and component_id in item["component_ids"]), None)
            if page:
                chosen.append(page)
                origins.add(self.source(page["url"]).origin_group)
        # Source diversity before second pages from an already selected family.
        # Diversity is applied within each relevance tier. A second governance
        # page must not lose to a funding article merely for publisher variety.
        tiers = sorted({tier_of(item) for item in candidates}, reverse=True)
        for tier in tiers:
            group = [item for item in candidates
                     if tier_of(item) == tier]
            for item in group:
                origin = self.source(item["url"]).origin_group
                if origin not in origins and item not in chosen:
                    chosen.append(item)
                    origins.add(origin)
            chosen.extend(item for item in group if item not in chosen)
        return chosen[:limit]

    async def extract_pages(self, pages):
        if not pages:
            return
        urls = [item["url"] for item in pages]
        for item in pages:
            self.component_pages_attempted.update(item["component_ids"])
        self.attempted.update(url_identity(url) for url in urls)
        self.trace.extraction_urls += len(urls)
        try:
            response = await providers.tavily_extract(self.client, urls, self.tavily_key, format="markdown")
        except PROVIDER_ERRORS:
            if any(self.source(url).eligible for url in urls):
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
                source = self.source(url)
                if not source.eligible:
                    self.event("lead_only_unverified_publisher", url)
                    for linked in original_links(text, self.claim):
                        if linked != url:
                            self.add({"url": linked, "title": "Linked original source",
                                      "score": 0.7}, "source_link")
                    continue
                jobs.append(self.select(self.pool[url_identity(url)], text, source))
            except (ValueError, TypeError, AttributeError):
                self.failure("page extractions")
        for url in set(urls) - seen:
            if not self.source(url).eligible:
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
                published_at=item["published_at"], date_context=self.date_context, claim_context=self.claim_context)
            self.reviewed_pages += 1
            details = {"reason": selection.reason[:600],
                       "applicability": selection.applicability,
                       "applicability_reason": selection.applicability_reason[:600]}
            if selection.relevance == "irrelevant":
                self.event("rejected_semantically_irrelevant", item["url"], **details)
                return
            self.evidence.append(EvidenceCandidate(
                evidence_id="source-" + sha256(item["url"].encode()).hexdigest()[:16],
                title=item["title"], url=item["url"], publisher=source.publisher,
                source_type=source.source_type, published_at=item["published_at"],
                retrieved_at=self.now, passage=passage,
                # Whole-pool reading (pipeline-v3) reads this text directly;
                # in-memory only, never persisted into results.
                full_text=text[:8000],
                # Fixed ranking weights, NOT LLM confidence or truth probabilities.
                retrieval_score=0.9 if selection.relevance == "direct" else 0.5,
                provenance=EvidenceProvenance(source_policy=source.policy,
                    source_reason=source.reason, origin_group=source.origin_group,
                    discovery_method=item["method"], relevance=selection.relevance,
                    relevance_reason=selection.reason, relevance_quote=selection.quote,
                    applicability=selection.applicability,
                    applicability_reason=selection.applicability_reason,
                    condition_quotes=selection.condition_quotes)))
            self.event("accepted_" + selection.relevance + "_" + selection.applicability, item["url"], **details)
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
                if official_forecast.eligible_context(self.claim_context, self.date_context):
                    try:
                        self.event("official_forecast_request", official_forecast.API_URL)
                        forecast = await official_forecast.retrieve_forecast(self.client, self.claim_context, self.date_context)
                        if forecast:
                            self.evidence.append(forecast)
                            self.event("accepted_official_forecast_" + forecast.provenance.applicability, official_forecast.API_URL)
                            if (forecast.provenance.applicability == "established"
                                    and not requires_weather_context_search(self.claim)):
                                result = _finish(self.evidence, self.warnings, False)
                                result.trace = self.trace
                                return result
                        else:
                            self.event("official_forecast_outside_claim_dates", official_forecast.API_URL)
                    except PROVIDER_ERRORS:
                        # Optional specialised data cannot turn successful web
                        # fallback into a provider outage by itself.
                        self.warnings.append("The current official forecast could not be used; other sources were checked.")
                        self.event("official_forecast_unavailable", official_forecast.API_URL)
                if official_climate.eligible(self.claim_context, self.date_context):
                    try:
                        record = await official_climate.retrieve_record(self.client, self.claim_context, self.date_context)
                        if record:
                            self.evidence.append(record)
                            self.event("accepted_official_climate_record", official_climate.RECORD_URL)
                    except PROVIDER_ERRORS:
                        self.warnings.append("The official historical temperature record could not be verified; no climate plausibility score was assigned.")
                        self.event("official_climate_unavailable", official_climate.RECORD_URL)
                if not (self.google_key and self.tavily_key and self.ollama_key):
                    self.failure("configured web fallback")
                    result = _finish(self.evidence, self.warnings, self.failed)
                    result.trace = self.trace
                    return result
                relation_queries = relationship_queries(self.search_claim)
                comparison_queries = ranking_queries(self.search_claim)
                focused_queries = relation_queries or comparison_queries
                await asyncio.gather(self.google(query), self.search(focused_queries[0] if focused_queries else query))
                await self.extract_pages(self.next_pages(1 if focused_queries or self.component_queries else 2, eligible_only=True))
                if self.component_queries or not enough_evidence(self.evidence):
                    # Use both alternative formulations when available. A planner
                    # failure still permits broad literal search.
                    async def expand():
                        try:
                            return await plan_queries(self.client, self.search_claim, self.ollama_key, allow_policy_lookup=True,
                                claim_context=self.claim_context, date_context=self.date_context,
                                coverage_gaps=missing_coverage(self.evidence, self.claim_context, self.date_context))
                        except PROVIDER_ERRORS:
                            self.failure("alternative query planning")
                            return []
                    weather = weather_queries(self.search_claim, self.claim_context, self.date_context)
                    entry_query = current_entry_query(self.search_claim)
                    if self.component_queries:
                        # Exactly the existing two follow-up slots, one per part.
                        # No new model call, search loop or assumed verdict.
                        alternatives = self.component_queries
                        self.event("material_component_searches")
                        anchor = component_discovery_anchor(self.claim)
                        if anchor:
                            self.event("component_discovery_scope", interpretation=anchor,
                                reason="Discovery context only; claim spans and evidence applicability remain unchanged.")
                    elif weather:
                        alternatives = weather
                    elif entry_query:
                        # Reserve the same two search slots for different jobs:
                        # the unchanged allegation/announcement and the current
                        # entry rule. Discovery never substitutes for assessment.
                        alternatives = [query[:378] + " official announcement", entry_query]
                    elif relation_queries:
                        alternatives = await expand() or [query, relation_queries[1]]
                    elif comparison_queries:
                        alternatives = [query, comparison_queries[1]]
                    else:
                        alternatives = await expand()
                    await asyncio.gather(*(self.search(value, broad=True)
                                           for value in (alternatives[:2] or [query])))
                    # Leave room to follow an eligible original from an unknown page.
                    while True:
                        # Only explicit per-page failures replenish slots. HTTP,
                        # response-contract and model failures do not earn retries.
                        budget = MAX_PAGES + min(len(self.unavailable_pages), MAX_REPLACEMENT_PAGES)
                        remaining = min(budget - len(self.attempted), MAX_PAGES - self.trace.relevance_calls)
                        if remaining <= 0:
                            break
                        # Observe failures before spending more slots at the
                        # same publisher. Subsequent batches re-rank its pages.
                        pages = self.next_pages(min(remaining, 2))
                        if len(pages) == 2 and self.source(pages[0]["url"]).origin_group == self.source(pages[1]["url"]).origin_group:
                            pages = pages[:1]
                        if not pages:
                            break
                        if any(not self.source(page["url"]).eligible for page in pages):
                            pages = pages[:1]
                        if len(self.attempted) + len(pages) > MAX_PAGES:
                            self.event("trying_alternative_source_pages")
                        await self.extract_pages(pages)
                        if enough_evidence(self.evidence) and (not self.component_queries
                                or self.component_pages_attempted >= {"event", "premise"}):
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
        if result.retrieval_status == "failed" and not self.failed and self.unavailable_pages:
            result.failure_reason = "source_pages_unavailable"
        result.trace = self.trace
        return result


async def retrieve_with_client(claim, client, google_key, tavily_key, ollama_key, *, date_context=None, claim_context=None):
    return await RetrievalRun(claim, client, google_key, tavily_key, ollama_key, date_context=date_context,
                              claim_context=claim_context).run()


async def live(claim, google_key, tavily_key, ollama_key, *, date_context=None, claim_context=None):
    async with httpx.AsyncClient(timeout=httpx.Timeout(20, connect=5), follow_redirects=False) as client:
        return await retrieve_with_client(claim, client, google_key, tavily_key, ollama_key, date_context=date_context,
                                          claim_context=claim_context)
