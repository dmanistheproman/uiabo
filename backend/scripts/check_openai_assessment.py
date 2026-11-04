"""Run one live claim with in-memory results; no Firebase writes or app allowance.

This command uses the configured retrieval/model services and can incur API costs.
It prints a bounded summary, not provider payloads, credentials or source text.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.pipeline.shared.errors import PipelineError


def _preflight():
    """Require the selected experiment; never silently switch a user's provider."""
    mode = os.environ.get('TEXT_ANALYSIS_MODE', 'pipeline').strip().lower()
    if mode == 'openai_web':
        from app.pipeline.evidence_assessment.openai_provider import get_settings
        return get_settings()
    if mode != 'pipeline':
        raise ValueError('Invalid text analysis mode')
    required = {
        "EVIDENCE_PIPELINE_V3": {"1", "true", "yes"},
        "EVIDENCE_VERIFICATION_ENABLED": {"1", "true", "yes"},
        "EVIDENCE_VERIFICATION_PROVIDER": {"openai"},
    }
    missing = [name for name, allowed in required.items()
               if os.environ.get(name, "").strip().lower() not in allowed]
    if missing:
        raise ValueError("Enable the OpenAI experiment settings in the root .env: " + ", ".join(missing))
    from app.pipeline.evidence_assessment.openai_provider import get_settings
    return get_settings()


def _make_pipeline():
    from app.pipeline.orchestration.dependencies import get_pipeline_orchestrator
    from app.pipeline.orchestration.repository import InMemoryResultRepository
    return get_pipeline_orchestrator().with_repository(
        InMemoryResultRepository(), run_recorder=lambda _: None)


def _token_count(value):
    if isinstance(value, bool):
        return 0
    try:
        count = int(value)
        return count if count >= 0 else 0
    except (TypeError, ValueError, OverflowError):
        return 0


def result_summary(result):
    """Use an explicit metadata allowlist; never echo source or request payloads."""
    record = result.model_dump(mode="json")
    decisions = (record.get("retrieval_trace") or {}).get("decisions", [])
    selected = [item for item in decisions
                if item.get("decision") in {"verification_provider_selected", "openai_web_research_selected"}]
    usage = [item for item in decisions
             if item.get("decision") in {"verification_provider_usage", "openai_web_research_usage"}
             and item.get("provider") == "openai"]
    totals = {name: sum(_token_count(item.get(name)) for item in usage)
              for name in ("input_tokens", "output_tokens", "total_tokens")}
    search_usage = [item for item in usage if 'billable_search_requests' in item]
    selected_openai = any(item.get("provider") == "openai" for item in selected)
    return {
        "status": "completed",
        "assessment_outcome": record.get("assessment_outcome"),
        "label": (record.get("credibility") or {}).get("label"),
        "explanation": (record.get("explanation") or "")[:4000],
        "pipeline_version": record.get("pipeline_version"),
        "research_verdict": (record.get('research_assessment') or {}).get('verdict'),
        "research_sources": [dict(title=source.get('title'), url=source.get('url'))
                             for source in (record.get('research_assessment') or {}).get('sources', [])],
        "web_search_calls": (record.get('retrieval_trace') or {}).get('search_requests', 0),
        "billable_search_requests": sum(_token_count(item['billable_search_requests'])
                                        for item in search_usage) if search_usage else None,
        "openai_selected": selected_openai,
        "openai_response_count": len(usage),
        "openai_models": sorted({item["model"] for item in usage if item.get("model")}),
        "openai_token_usage": totals if usage else None,
        "assessment_note": (
            "OpenAI response metadata was recorded; this does not by itself establish verdict correctness."
            if usage else
            "OpenAI was selected, but no completed response metadata was recorded."
            if selected_openai else
            "This result did not use the joint OpenAI verifier. No-evidence, uncheckable and specialist routes can bypass it."
        ),
    }


def run_check(text):
    started = time.perf_counter()
    try:
        settings = _preflight()
        summary = result_summary(_make_pipeline().analyze(text))
        summary["configured_model"] = settings.model
        code = 0
    except PipelineError as error:
        summary = {"status": "failed", "error_code": error.error_code,
                   "stage": error.stage, "message": error.message,
                   "retryable": error.retryable}
        code = 1
    except ValueError:
        # Only local preflight generates this exception here. Avoid echoing
        # arbitrary exception messages if a dependency raises ValueError later.
        summary = {"status": "failed", "error_code": "EXPERIMENT_CONFIGURATION_INVALID",
                   "message": "Check the OpenAI experiment settings in the root .env and restart. See OPENAI_ASSESSMENT_SETUP.md."}
        code = 1
    except Exception as error:
        from app.pipeline.evidence_assessment.openai_provider import OpenAIProviderError
        if isinstance(error, OpenAIProviderError):
            summary = {"status": "failed", "error_code": error.code,
                       "message": error.message, "retryable": error.retryable}
        else:
            summary = {"status": "failed", "error_code": "DIAGNOSTIC_FAILED",
                       "error_type": type(error).__name__,
                       "message": "The diagnostic could not complete. No raw provider error was printed."}
        code = 1
    summary["elapsed_seconds"] = round(time.perf_counter() - started, 2)
    summary["saved_to_firebase"] = False
    summary["app_allowance_used"] = False
    return summary, code


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", required=True, help="One English factual claim to check.")
    args = parser.parse_args(argv)
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
    summary, code = run_check(args.text)
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
