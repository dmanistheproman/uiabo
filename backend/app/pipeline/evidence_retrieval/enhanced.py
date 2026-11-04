"""Opt-in web retrieval: discover broadly, extract originals, assess eligibility.

Normally three Tavily searches, one Google request and four semantic relevance
calls, with up to two extraction replacements for unavailable pages. A scoped
coverage gap permits one recovery search and two further reviews; the same
65-second total deadline applies.
A successful but inconclusive search is not an outage.
Partial validated evidence survives a later timeout with an explicit warning.
"""

import asyncio
from datetime import datetime, timezone
from hashlib import sha256
import math
import re

import httpx
from pydantic import ValidationError
from app.pipeline.shared.runtime_budget import remaining_seconds
from pypdf.errors import PyPdfError

from app.pipeline.shared.models import CoverageIssue, EvidenceCandidate, EvidenceProvenance, RetrievalTrace
from . import providers, official_forecast, official_climate
from . import topic_scope, pdf_reader
from .extraction_scope import (html_alternative, needs_advanced, unrelated_policing_page,
                               UNAVAILABLE_WARNING, LEAD_WARNING)
from app.pipeline.shared.jurisdiction import scoped_query
from .coverage import missing_coverage, requires_weather_context_search, weather_queries, weather_page_priority
from .query_planning import format_search_amounts, plan_queries
from .passport_entry import current_entry_query, entry_page_priority
from .relevance import select_with_client, assessment_excerpt
from .requirements import plan_queries as verification_queries, focus_text, document_priority, methodology_document
from .service import _date, _deduplicate, _finish, relevance, PROVIDER_ERRORS
from .source_policy import classify_source, extractable_lead, original_links, public_url, url_identity, preferred_corporate_domains
from app.pipeline.shared.dates import dated_search_claim
from app.pipeline.shared.interpretation import relationship_queries, relationship_page_priority, control_wording, claim_relationship, corporate_search_text
from app.pipeline.shared.rankings import ranking_queries, ranking_page_priority, political_salary_ranking
from app.pipeline.shared.components import component_queries, component_discovery_anchor, component_page_priority, cpf_retirement_context
from .sources import SOURCES
from app.pipeline.shared.public_changes import public_change_plan, page_priority, baseline_section
from app.pipeline.shared.statistical_dates import uses_latest_statistics

VERSION = "retrieval-web-v25-source-versions"
TOTAL_TIMEOUT_SECONDS = 65.0
MAX_PAGES = 4
MAX_REPLACEMENT_PAGES = 2


def enough_evidence(items):
    return len({item.provenance.origin_group for item in _deduplicate(items)
        if item.provenance and item.provenance.relevance == "direct"
        and item.provenance.applicability == "established"}) >= 2


class RetrievalRun:
    def __init__(self, claim, client, google_key, tavily_key, ollama_key, *, date_context=None, claim_context=None,
                 verification_plan=None):
        self.claim, self.client = claim, client
        self.date_context = date_context
        self.claim_context = claim_context
        self.verification_plan = verification_plan
        self.requirement_queries = verification_queries(verification_plan)
        self.repair_queries = []
        self.component_queries = component_queries(claim)
        self.component_pages_attempted = set()
        self.search_claim = dated_search_claim(claim, date_context)
        self.google_key, self.tavily_key, self.ollama_key = google_key, tavily_key, ollama_key
        self.trace = RetrievalTrace()
        self.trace_limit = 80
        self.evidence, self.warnings = [], []
        self.pool, self.attempted = {}, set()
        self.failed = False
        self.unavailable_pages = set()
        self.reviewed_pages = 0
        self.advanced_pages = 0
        self.pdf_reads = 0
        self.native_pdf_reads = 0
        self.dataset_reads = 0
        self.alternatives = {}
        self.now = claim_context.assessed_at if claim_context else datetime.now(timezone.utc)
        self.public_change = public_change_plan(claim, claim_context, date_context)
        self.topic_queries = topic_scope.topic_queries(claim, claim_context)
        if self.component_queries and self.topic_queries and claim_context and claim_context.retrieval_topic == 'employment':
            self.component_queries = self.topic_queries

    def event(self, decision, url="", **details):
        if len(self.trace.decisions) < self.trace_limit:
            self.trace.decisions.append({"decision": decision, "url": url, **details})

    def source(self, url):
        return classify_source(url, self.claim)

    def failure(self, stage, *, optional=False):
        if not optional:
            self.failed = True
        message = f"Some {stage} could not be completed; any returned evidence was validated separately."
        if message not in self.warnings:
            self.warnings.append(message)
            self.trace.coverage_issues.append(CoverageIssue(warning=message,
                stage='search' if 'search' in stage else 'selection' if 'relevance' in stage else 'other',
                blocks_inference=not optional,
                reason=f'The {stage} did not complete. Required coverage cannot be assumed.'))
        self.event('optional_provider_failure' if optional else 'provider_failure', stage=stage)

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
            content = item.get('content', '') if isinstance(item.get('content', ''), str) else ''
            mismatch = topic_scope.mismatched_jurisdiction(self.claim_context, url, title + ' ' + content)
            if mismatch:
                self.event('rejected_candidate_jurisdiction', url, reason=mismatch)
                return
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
        component_id = ("event", "premise")[self.component_queries.index(query)] if query in self.component_queries else None
        notice_query = bool(self.public_change and query in self.public_change['queries'])
        original_query = query
        if uses_latest_statistics(self.claim) and not self.requirement_queries and not self.repair_queries:
            query = query[:355] + ' latest official statistics comparison'
        query = scoped_query(query, self.claim_context)
        self.trace.search_requests += 1
        self.event("web_search" if broad else "preferred_search", query=query)
        try:
            domains = self.public_change['domains'] if notice_query else preferred_corporate_domains(self.claim) if not broad else None
            if not domains and not broad:
                domains = topic_scope.domains_for(self.claim_context) or None
            if not broad and political_salary_ranking(self.claim):
                domains = [*SOURCES, "politicalsalaries.com"]
            options = {"preferred_domains": domains} if domains else {}
            items = await providers.tavily_search(self.client, query, self.tavily_key, broad=broad and not notice_query, **options)
            for item in items:
                self.add(item, "web_search" if broad else "preferred_search", component_id=component_id)
            if notice_query:
                self.event("public_notice_search_completed", query=original_query, results=str(len(items)))
        except PROVIDER_ERRORS:
            self.failure("web searches")

    async def google(self, query):
        if not self.google_key:
            self.event('optional_fact_check_not_configured')
            return
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
            self.failure("fact-check searches", optional=True)

    def next_pages(self, limit, *, eligible_only=False):
        unavailable_origins = {self.source(url).origin_group for url in self.unavailable_pages}
        ownership_control = control_wording(self.claim) and claim_relationship(self.claim) == 'ownership'
        read_publishers = {item.publisher for item in self.evidence}
        def tier_of(item):
            return (self.source(item["url"]).eligible,
                    item['url'] in self.alternatives,
                    document_priority(self.claim, item, self.verification_plan, self.repair_queries),
                    max((relevance(q, item['title'] + ' ' + item['content'])
                         for q in self.repair_queries or self.requirement_queries), default=0),
                    topic_scope.page_priority(self.claim_context, self.claim, item['title'], item['url'], item['content'], self.now.date()),
                    self.source(item["url"]).origin_group not in unavailable_origins,
                    page_priority(self.public_change, item['title'], item['url'], item['content']),
                    component_page_priority(self.claim, item["title"], item["url"], item["content"], as_of=self.now.date()),
                    (self.source(item['url']).publisher not in read_publishers) if ownership_control else False,
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
        for component_id in (("premise", "event") if self.component_queries
                             and not self.requirement_queries and not self.repair_queries else ()):
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
        from . import datasets
        native = [p for p in pages if datasets.dataset_id(p['url'])][:max(0, 2 - self.dataset_reads)]
        self.dataset_reads += len(native)
        pages = [p for p in pages if p not in native]
        # At most two expensive document extractions, within the existing page
        # and wall-clock budgets. Keep basic/advanced pages in separate batches.
        advanced = [p for p in pages if needs_advanced(p, self.claim_context)][:max(0, 2 - self.advanced_pages)]
        basic = [p for p in pages if p not in advanced]
        self.advanced_pages += len(advanced)
        jobs = [self._extract_dataset(p) for p in native]
        if advanced:
            jobs.append(self._extract_batch(advanced, depth='advanced'))
        if basic:
            jobs.append(self._extract_batch(basic))
        await asyncio.gather(*jobs)

    async def _extract_dataset(self, item):
        from .datasets import read_dataset, needs_catalogue_context, catalogue_context
        try:
            text = await read_dataset(item['url'], focus_text(self.claim, self.verification_plan, self.repair_queries))
        except PROVIDER_ERRORS:
            # Native API and the HTML extractor are independent. A public API
            # failure does not cancel other providers or fabricate empty rows.
            self.event('native_dataset_unavailable', item['url'])
            await self._extract_batch([item])
            return
        if needs_catalogue_context(text):
            try:
                # Generic columns (DataSeries + years, for example) omit the
                # population/metric definition. Read the SAME catalogue page;
                # a search-result title is not a verified table definition.
                async with asyncio.timeout(5):
                    response = await providers.tavily_extract(self.client, [item['url']], self.tavily_key,
                                                              format='markdown')
                matching = [r for r in response['results'] if isinstance(r, dict) and r.get('url') == item['url']]
                context = catalogue_context(matching[0].get('raw_content', '')) if len(matching) == 1 else ''
                if context:
                    available = 6000 - len(context) - 2
                    if len(text) > available:
                        text = text[:available].rsplit('\n', 1)[0]
                    text = context + '\n\n' + text
                    self.event('native_dataset_catalogue_context_read', item['url'])
                else:
                    self.event('native_dataset_catalogue_context_missing', item['url'])
            except PROVIDER_ERRORS:
                # Keep valid rows. Their unidentified metric/population must
                # remain an assessment gap, never guessed from discovery text.
                self.event('native_dataset_catalogue_context_unavailable', item['url'])
        self.attempted.add(url_identity(item['url']))
        self.component_pages_attempted.update(item['component_ids'])
        self.trace.extraction_urls += 1
        self.event('native_dataset_rows_read', item['url'])
        await self.select({**item, 'method': 'official_api'}, text, self.source(item['url']))

    async def _extract_batch(self, pages, *, depth='basic'):
        urls = [item["url"] for item in pages]
        for item in pages:
            self.component_pages_attempted.update(item["component_ids"])
        self.attempted.update(url_identity(url) for url in urls)
        self.trace.extraction_urls += len(urls)
        try:
            self.event('extraction_batch', depth=depth, pages=str(len(urls)))
            options = {'depth': depth} if depth != 'basic' else {}
            response = await providers.tavily_extract(self.client, urls, self.tavily_key, format="markdown", **options)
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
                # Eligible journalism/government pages can cite the actual
                # research, dataset or policy. Preserve literal primary links
                # as discovery candidates within the existing page budget.
                for linked in original_links(text, self.claim):
                    position = text.find(linked)
                    nearby = text[max(0, position - 250):position + len(linked) + 250]
                    if linked != url and relevance(self.claim, nearby) >= .15:
                        self.add({'url': linked, 'title': 'Referenced source: ' + self.pool[url_identity(url)]['title'],
                                  'score': .65, 'content': nearby}, 'source_link')
                mismatch = topic_scope.mismatched_jurisdiction(self.claim_context, url, text[:60000])
                if mismatch:
                    self.reviewed_pages += 1
                    self.event('rejected_page_jurisdiction', url, reason=mismatch)
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
            item = self.pool[url_identity(url)]
            if (not self.native_pdf_reads and pdf_reader.eligible(item, self.claim_context, self.verification_plan)):
                # An unreadable provider extraction may still be an ordinary
                # short, native PDF. Preserve the same host/size/page guards.
                self.native_pdf_reads += 1
                try:
                    async with asyncio.timeout(10):
                        content = await pdf_reader.download(url, self.claim)
                        texts = await asyncio.to_thread(pdf_reader.native_pages, content)
                    self.event('native_pdf_extraction_recovered', url)
                    self.unavailable_pages.discard(url)
                    jobs.append(self.select(item, '\n\n'.join(texts), self.source(url)))
                    continue
                except PROVIDER_ERRORS + (PyPdfError,):
                    self.event('native_pdf_extraction_unavailable', url)
            unrelated = unrelated_policing_page(item, self.claim_context, self.claim)
            self.trace.coverage_issues.append(CoverageIssue(warning=UNAVAILABLE_WARNING,
                stage='extraction', url=url, blocks_inference=not unrelated,
                reason=('The failed page describes an unrelated offence; it supplies no baseline or notice coverage.'
                        if unrelated else 'An official candidate could not be read; its contents remain unknown.')))
            alternate = html_alternative(url)
            if alternate and url_identity(alternate) not in self.attempted:
                self.add({**item, 'url': alternate}, item['method'])
                self.alternatives[alternate] = url
                self.event('equivalent_html_scheduled', alternate, original=url)
        if jobs:
            await asyncio.gather(*jobs)

    async def select(self, item, text, source):
        self.trace.relevance_calls += 1
        try:
            selection_text = baseline_section(self.public_change, item['url'], text)
            options = {}
            if self.verification_plan:
                options['verification_plan'] = self.verification_plan
            if self.repair_queries:
                options['repair_queries'] = self.repair_queries
            selection, passage = await select_with_client(self.client, self.claim, selection_text,
                self.ollama_key, as_of=self.date_context.as_of if self.date_context else self.now.date(),
                published_at=item["published_at"], date_context=self.date_context, claim_context=self.claim_context,
                source_url=item['url'],
                **options)
            self.reviewed_pages += 1
            if item['url'] in self.alternatives and selection.relevance != 'irrelevant':
                original = self.alternatives[item['url']]
                for issue in self.trace.coverage_issues:
                    if issue.url == original:
                        issue.resolved_by = item['url']
                self.event('equivalent_document_reviewed', item['url'], original=original)
            mismatch = topic_scope.guard_selection(selection, passage, self.claim_context, item['url'], self.claim)
            if mismatch:
                self.event('rejected_passage_jurisdiction', item['url'], reason=mismatch)
                return
            details = {"reason": selection.reason[:600],
                       "applicability": selection.applicability,
                       "applicability_reason": selection.applicability_reason[:600]}
            if selection.relevance == "irrelevant":
                self.event("rejected_semantically_irrelevant", item["url"], **details)
                return
            # Short statistical documents often put the period/population above
            # a chart, outside the selected 1,800-character window. Keep the
            # entire literal document when bounded, not a reconstructed table.
            if (not self.requirement_queries and self.claim_context and self.claim_context.retrieval_topic == 'employment'
                    and needs_advanced(item, self.claim_context) and len(text) <= 12000):
                passage = text.strip()
                self.event('retained_statistical_document_context', item['url'])
            if item['method'] == 'official_api' and len(text) <= 6000:
                # A structured dataset's selected rows must stay attached to
                # their literal field names; an HTML preview heading is not data.
                passage = text.strip()
                self.event('retained_native_dataset_headers_and_rows', item['url'])
            if self.requirement_queries:
                passage = assessment_excerpt(self.claim, text, passage,
                    verification_plan=self.verification_plan, repair_queries=self.repair_queries, limit=6000)
                self.event('retained_requirement_sections', item['url'])
            candidate = EvidenceCandidate(
                evidence_id="source-" + sha256(item["url"].encode()).hexdigest()[:16],
                title=item["title"], url=item["url"], publisher=source.publisher,
                source_type=source.source_type, published_at=item["published_at"],
                retrieved_at=self.now, passage=passage,
                # Whole-pool reading (pipeline-v3) reads this text directly;
                # in-memory only, never persisted into results.
                full_text=assessment_excerpt(self.claim, text, passage, verification_plan=self.verification_plan,
                                             repair_queries=self.repair_queries),
                # Fixed ranking weights, NOT LLM confidence or truth probabilities.
                retrieval_score=0.9 if selection.relevance == "direct" else 0.5,
                provenance=EvidenceProvenance(source_policy=source.policy,
                    source_reason=source.reason, origin_group=source.origin_group,
                    discovery_method=item["method"], relevance=selection.relevance,
                    relevance_reason=selection.reason, relevance_quote=selection.quote,
                    applicability=selection.applicability,
                    applicability_reason=selection.applicability_reason,
                    condition_quotes=selection.condition_quotes))
            # Publish literal evidence before the optional fallback so a timeout
            # cannot discard already validated source text.
            self.evidence.append(candidate)
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

    async def enrich_pdf(self):
        candidates = [s for s in self.evidence if pdf_reader.eligible(
            {'url': str(s.url), 'title': s.title, 'content': s.passage[:1000]}, self.claim_context,
            self.verification_plan)]
        # Definitions may be useful textual context but must not consume the
        # sole visual chart-reading slot intended for measured observations.
        candidates = [s for s in candidates if not methodology_document(s.title, s.url)]
        if not candidates or self.pdf_reads:
            return
        # Choose after all semantic reviews, rather than awarding the sole slot
        # to whichever concurrent review happens to finish first.
        def priority(s):
            return (topic_scope.page_priority(self.claim_context, self.claim, s.title, str(s.url),
                        s.full_text or s.passage, self.now.date()),
                    relevance(self.claim, s.title), s.published_at or self.now.date().min,
                    -len(s.full_text or s.passage))
        candidate = max(candidates, key=priority)
        self.pdf_reads += 1
        self.event('pdf_reading_started', str(candidate.url))
        reading, status = await pdf_reader.read_pdf(str(candidate.url), self.claim)
        candidate.pdf_reading = reading
        self.event('pdf_reading_' + status, str(candidate.url))
        if reading is None:
            self.warnings.append('The PDF chart could not be read reliably. Its extracted text remains available, but chart relationships were not verified.')

    async def run(self):
        query = scoped_query(format_search_amounts(" ".join(self.search_claim.split()))[:400], self.claim_context)
        if self.claim_context and self.claim_context.jurisdiction:
            self.event('jurisdiction_resolved', jurisdiction=self.claim_context.jurisdiction,
                       basis=self.claim_context.jurisdiction_basis, topic=self.claim_context.retrieval_topic)
        if self.public_change and self.public_change['kind'] == 'airport_closure' and query.lower().startswith('the airport'):
            query = 'Changi Airport' + query[len('the airport'):]
        try:
            async with asyncio.timeout(remaining_seconds(TOTAL_TIMEOUT_SECONDS)):
                if official_forecast.eligible_context(self.claim_context, self.date_context):
                    try:
                        self.event("official_forecast_request", official_forecast.API_URL)
                        forecast = await official_forecast.retrieve_forecast(self.client, self.claim_context, self.date_context)
                        if forecast:
                            self.evidence.append(forecast)
                            self.event("accepted_official_forecast_" + forecast.provenance.applicability, official_forecast.API_URL)
                            if (forecast.provenance.applicability == "established"
                                    and not requires_weather_context_search(self.claim)
                                    and not official_climate.eligible(self.claim_context, self.date_context)):
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
                if not (self.tavily_key and self.ollama_key):
                    self.failure("configured web fallback")
                    result = _finish(self.evidence, self.warnings, self.failed)
                    result.trace = self.trace
                    return result
                relation_queries = relationship_queries(self.search_claim)
                comparison_queries = ranking_queries(self.search_claim)
                focused_queries = relation_queries or comparison_queries
                ambiguous = claim_relationship(self.claim) == 'ambiguous_control'
                if ambiguous and 'singapore airlines' in corporate_search_text(self.claim).lower():
                    for url, title in [
                        ('https://www.temasek.com.sg/en/about-us/history-of-temasek', 'Corporate governance and history'),
                        ('https://www.singaporeair.com/en_UK/sg/about-us/information-for-investors/shareholding-info', 'Current shareholding information')]:
                        self.add({'url': url, 'title': title, 'score': 1}, 'preferred_search')
                ownership_control = control_wording(self.claim) and claim_relationship(self.claim) == 'ownership'
                if ownership_control and 'singapore airlines' in corporate_search_text(self.claim).lower():
                    self.add({'url': 'https://www.singaporeair.com/en_UK/sg/about-us/information-for-investors/shareholding-info',
                              'title': 'Current stock and shareholding information', 'score': 1}, 'preferred_search')
                if self.public_change:
                    for url in self.public_change['baseline_urls']:
                        self.add({'url': url, 'title': 'Official current operating or entry requirements', 'score': 1}, 'preferred_search')
                initial_query = (self.requirement_queries[0] if self.requirement_queries else
                                 focused_queries[0] if focused_queries else query)
                if self.requirement_queries:
                    self.event('verification_plan_discovery', queries=str(len(self.requirement_queries)))
                await asyncio.gather(self.google(query), self.search(initial_query))
                await self.extract_pages(self.next_pages(1 if self.requirement_queries or focused_queries or self.component_queries or self.topic_queries else 2, eligible_only=True))
                if self.requirement_queries or self.public_change or self.component_queries or not enough_evidence(self.evidence):
                    # Use both alternative formulations when available. A planner
                    # failure still permits broad literal search.
                    async def expand():
                        try:
                            options = ({'discovery_evidence': [(s.full_text or s.passage)[:4000] for s in self.evidence[:2]]}
                                       if ownership_control else {})
                            return await plan_queries(self.client, self.search_claim, self.ollama_key, allow_policy_lookup=True,
                                claim_context=self.claim_context, date_context=self.date_context,
                                coverage_gaps=missing_coverage(self.evidence, self.claim_context, self.date_context), **options)
                        except PROVIDER_ERRORS:
                            self.failure("alternative query planning")
                            return []
                    weather = weather_queries(self.search_claim, self.claim_context, self.date_context)
                    entry_query = current_entry_query(self.search_claim)
                    if self.public_change:
                        # The established public-notice inference requires
                        # these two successfully completed official searches.
                        # Plan queries still guide the first search and any
                        # later assessment-driven repair; do not replace the
                        # coverage proof with merely similar query wording.
                        alternatives = self.public_change['queries']
                    elif self.requirement_queries:
                        alternatives = self.requirement_queries[1:3] or [query]
                    elif self.component_queries:
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
                        alternatives = [relation_queries[1], relation_queries[0]] if ambiguous else await expand() or [query, relation_queries[1]]
                        if ownership_control:
                            # Reserve the other slot for the ultimate owner link;
                            # the adaptive first query can follow a newly found holder.
                            alternatives = [alternatives[0], relation_queries[1]]
                    elif comparison_queries:
                        alternatives = [query, comparison_queries[1]]
                    elif self.topic_queries:
                        alternatives = self.topic_queries
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
                        if not self.requirement_queries and enough_evidence(self.evidence) and (not self.component_queries
                                or self.component_pages_attempted >= {"event", "premise"}):
                            break
                # One bounded repair search only for an identified local-topic
                # gap. Two extra passage reviews replace unrelated/unreadable
                # pages; no provider-outage retries or unbounded search loop.
                # Planned claims use the later assessor-driven repair. Legacy
                # claims retain this local recovery, even after one provider
                # failed: healthy search/extraction services can still fill it.
                repair = (None if self.requirement_queries else
                          topic_scope.recovery_query(self.claim, self.evidence, self.claim_context))
                if repair and self.tavily_key and self.ollama_key:
                    self.event('targeted_coverage_recovery', query=repair,
                               gaps='; '.join(topic_scope.coverage_gaps(self.claim, self.evidence, self.claim_context))[:600])
                    await self.search(repair)
                    remaining = min(2, 6 - self.trace.relevance_calls, 8 - len(self.attempted))
                    await self.extract_pages(self.next_pages(max(0, remaining), eligible_only=True))
                for gap in topic_scope.coverage_gaps(self.claim, self.evidence, self.claim_context):
                    self.event('unresolved_coverage_gap', reason=gap)
                await self.enrich_pdf()
        except TimeoutError:
            self.failure("retrieval within its time limit")
        if any(event["decision"] == "lead_only_unverified_publisher" for event in self.trace.decisions):
            self.warnings.append(LEAD_WARNING)
            self.trace.coverage_issues.append(CoverageIssue(warning=LEAD_WARNING, stage='discovery',
                blocks_inference=False, reason='Unverified publishers were discovery leads only. Inference still requires successful official searches and an applicable baseline.'))
        # Only exact copies are removed here. Near-identical text can contain
        # decisive negation/quantity changes; do not discard it on word overlap.
        if self.unavailable_pages:
            self.warnings.append(UNAVAILABLE_WARNING)
        result = _finish(self.evidence, self.warnings,
            self.failed or bool(self.unavailable_pages and not self.reviewed_pages))
        if result.retrieval_status == "failed" and not self.failed and self.unavailable_pages:
            result.failure_reason = "source_pages_unavailable"
        result.trace = self.trace
        return result


async def retrieve_with_client(claim, client, google_key, tavily_key, ollama_key, *, date_context=None, claim_context=None,
                               verification_plan=None):
    return await RetrievalRun(claim, client, google_key, tavily_key, ollama_key, date_context=date_context,
                              claim_context=claim_context, verification_plan=verification_plan).run()


async def live(claim, google_key, tavily_key, ollama_key, *, date_context=None, claim_context=None, verification_plan=None):
    async with httpx.AsyncClient(timeout=httpx.Timeout(20, connect=5), follow_redirects=False) as client:
        return await retrieve_with_client(claim, client, google_key, tavily_key, ollama_key, date_context=date_context,
                                          claim_context=claim_context, verification_plan=verification_plan)
