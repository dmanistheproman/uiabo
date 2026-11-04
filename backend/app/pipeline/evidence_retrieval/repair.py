"""One assessment-driven, bounded retrieval pass. No verdicts are invented here."""

import asyncio
import re
import time

import httpx

from app.pipeline.shared.models import RetrievalTrace
from app.pipeline.shared.runtime_budget import remaining_seconds
from .enhanced import RetrievalRun
from .requirements import clean_queries
from .service import _finish, relevance
from .source_policy import url_identity
from .relevance import source_windows

TIMEOUT_SECONDS = 35.0
MAX_NEW_PAGES = 3
MAX_POOL = 6


def retained_pool(previous, additions, queries):
    """Keep strong sources and make room for useful gap-specific evidence.

    Scores here rank retrieval utility, never credibility. The next assessment
    must still establish the stance and scope of every retained passage.
    """
    old_ids = {s.evidence_id for s in previous}
    def priority(source):
        p = source.provenance
        established = bool(p and p.applicability == 'established')
        direct = bool(p and p.relevance == 'direct')
        gap_relevance = max((relevance(q, source.title + ' ' + source.passage) for q in queries), default=0)
        return (bool(source.forecast or source.climate_record),
                established and direct, established, direct,
                gap_relevance, source.evidence_id not in old_ids, source.retrieval_score)
    versions = {s.evidence_id: s for s in previous}
    for source in additions:
        old = versions.get(source.evidence_id)
        if old is None or old.passage in source.passage and len(source.passage) > len(old.passage):
            versions[source.evidence_id] = source
    candidates = sorted(versions.values(), key=priority, reverse=True)
    kept, urls, identifiers, passages = [], set(), set(), set()
    for source in candidates:
        url = url_identity(str(source.url))
        passage = ' '.join(source.passage.casefold().split())
        if url in urls or source.evidence_id in identifiers or passage in passages:
            continue
        kept.append(source)
        urls.add(url); identifiers.add(source.evidence_id); passages.add(passage)
        if len(kept) == MAX_POOL:
            break
    return kept


def reselect_existing(claim, previous, queries):
    """Expose already-fetched, novel source text; never synthesize an answer."""
    revised = []
    for source in previous:
        if not source.full_text or len(source.passage) > 6000:
            continue
        old_words = set(re.findall(r'\w+', source.passage.casefold()))
        windows = source_windows('\n'.join(queries), source.full_text)
        ranked = sorted(windows, key=lambda text: max(relevance(q, text) for q in queries), reverse=True)
        additions = []
        for text in ranked:
            novel_words = set(re.findall(r'\w+', text.casefold())) - old_words
            if (text not in source.passage and len(novel_words) >= 5
                    and max(relevance(q, text) for q in queries) >= .2):
                additions.append(text)
                break
        if additions:
            copy = source.model_copy(deep=True)
            copy.passage += '\n\n' + additions[0]
            revised.append(copy)
        if len(revised) == 2:
            break
    return revised


async def retrieve_with_client(claim, previous, queries, client, tavily_key, ollama_key):
    """Inject client/provider functions in tests; previous is never mutated."""
    result = previous.model_copy(deep=True)
    bounded = clean_queries(queries)
    run = RetrievalRun(claim.extracted_claim, client, '', tavily_key, ollama_key,
                       date_context=claim.date_context, claim_context=claim.claim_context,
                       verification_plan=getattr(claim, 'verification_plan', None))
    run.trace = result.trace or RetrievalTrace()
    run.trace_limit = 120
    run.repair_queries = bounded
    run.attempted = {url_identity(str(s.url)) for s in result.evidence}
    # Avoid fetching a previously discarded source again during the same run.
    for event in run.trace.decisions:
        if event.get('decision', '').startswith(('accepted_', 'rejected_semantically_', 'relevance_failed_')) and event.get('url'):
            try:
                run.attempted.add(url_identity(event['url']))
            except ValueError:
                pass
    run.event('assessment_driven_repair_started', queries=str(len(bounded)), max_new_pages=str(MAX_NEW_PAGES))
    if not bounded:
        run.event('assessment_driven_repair_skipped', reason='No valid distinct missing-evidence queries.')
        result.trace = run.trace
        return result
    refreshed = reselect_existing(claim.extracted_claim, result.evidence, bounded)
    run.evidence.extend(refreshed)
    for source in refreshed:
        run.event('existing_source_reselected_for_gap', str(source.url))
    started = time.monotonic()
    if not tavily_key or not ollama_key:
        run.failure('configured evidence repair')
    else:
        try:
            async with asyncio.timeout(remaining_seconds(TIMEOUT_SECONDS)):
                # Neither an optional fact-check outage nor a failed first
                # query prevents another independent query/provider succeeding.
                await asyncio.gather(*(run.search(q, broad=True) for q in bounded))
                start_attempted = len(run.attempted)
                while len(run.attempted) - start_attempted < MAX_NEW_PAGES:
                    remaining = MAX_NEW_PAGES - (len(run.attempted) - start_attempted)
                    pages = run.next_pages(remaining, eligible_only=True)
                    if not pages:
                        break
                    await run.extract_pages(pages)
                # The initial pass already has one optional PDF budget. A
                # repair may enrich a newly found short PDF only if the full
                # bounded read fits; it never delays retaining literal text.
                if TIMEOUT_SECONDS - (time.monotonic() - started) >= 23:
                    await run.enrich_pdf()
        except TimeoutError:
            run.failure('evidence repair within its time limit')
            run.event('assessment_driven_repair_timed_out')
    previous_ids = {s.evidence_id for s in result.evidence}
    run.event('assessment_driven_repair_finished',
              new_sources=str(sum(s.evidence_id not in previous_ids for s in run.evidence)),
              reselected_sources=str(len(refreshed)),
              outcome='partial_failure' if run.failed or run.unavailable_pages else 'searched')
    if run.unavailable_pages:
        from .extraction_scope import UNAVAILABLE_WARNING
        run.warnings.append(UNAVAILABLE_WARNING)
    merged = retained_pool(result.evidence, run.evidence, bounded)
    warnings = list(dict.fromkeys([*result.warnings, *run.warnings]))
    finished = _finish(merged, warnings,
                       run.failed or previous.retrieval_status == 'failed' or bool(run.unavailable_pages))
    finished.trace = run.trace
    return finished


async def live(claim, previous, queries, tavily_key, ollama_key):
    async with httpx.AsyncClient(timeout=httpx.Timeout(12, connect=4), follow_redirects=False) as client:
        return await retrieve_with_client(claim, previous, queries, client, tavily_key, ollama_key)
