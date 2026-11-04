"""Live retrieval/assessment diagnostics. No Firebase writes or user allowance."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

CASES = {
    'policing': 'Police will begin issuing fines to people who criticise government policies on social media if their posts receive more than 10,000 views.',
    'subsidies': 'From 2027, households living in private property will no longer receive any government subsidies, including healthcare subsidies.',
    'graduates': 'A leaked report claims unemployment among Singapore graduates has doubled because companies are hiring foreigners at half the salary.',
}


def check(name, text):
    from app.pipeline.claim_analysis.pool_v3 import analyse_claim_v3
    from app.pipeline.evidence_retrieval.service import retrieve_evidence
    from app.pipeline.evidence_assessment.pool import assess_pool_evidence
    from app.pipeline.shared.models import PreparedText
    from app.pipeline.shared.context import build_claim_context
    from app.pipeline.shared.dates import infer_date_context
    start = time.monotonic()
    result = {'case': name, 'submitted_text': text, 'checked_at': datetime.now(timezone.utc).isoformat()}
    try:
        # Public English fixtures isolate the claim/retrieval/assessment stages.
        claim = analyse_claim_v3(PreparedText(original_text=text, normalised_text=text, language='en'))
        # The production orchestrator attaches this server-owned context after
        # extraction. Mirror that step with one submission clock.
        now = datetime.fromisoformat(result['checked_at'])
        if claim.checkable:
            claim.date_context = infer_date_context(claim.extracted_claim, now)
            claim.claim_context = build_claim_context(claim.extracted_claim, now, original_text=text)
        claim = type(claim).model_validate(claim.model_dump())
        result['claim'] = claim.model_dump(mode='json')
        retrieval = retrieve_evidence(claim, mode='web')
        result['retrieval'] = retrieval.model_dump(mode='json', exclude={'evidence': {'__all__': {'full_text'}}})
        result['assessment'] = assess_pool_evidence(claim, retrieval).model_dump(mode='json')
        result['retrieval'] = retrieval.model_dump(mode='json', exclude={'evidence': {'__all__': {'full_text'}}})
    except Exception as error:
        # Do not print provider responses/headers, URLs with tokens or secrets.
        result['error_type'] = type(error).__name__
        result['error_code'] = getattr(error, 'error_code', None)
    result['elapsed_seconds'] = round(time.monotonic() - start, 1)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Allow calls to the configured providers (uses their quota).')
    parser.add_argument('--case', choices=CASES)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.live:
        parser.error('--live is required to call external providers')
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env', override=False)
    chosen = {args.case: CASES[args.case]} if args.case else CASES
    results = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = [pool.submit(check, key, value) for key, value in chosen.items()]
        for job in as_completed(jobs):
            item = job.result()
            results.append(item)
            print(json.dumps({'case': item['case'], 'outcome': item.get('assessment', {}).get('assessment_outcome'),
                'sources': len(item.get('retrieval', {}).get('evidence', [])),
                'elapsed_seconds': item['elapsed_seconds'], 'error': item.get('error_type')}), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2), encoding='utf-8')
