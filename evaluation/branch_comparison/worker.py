"""One isolated evaluation request. Never instantiate the FastAPI application."""
import argparse
import contextlib
from datetime import datetime
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time

FORECAST_URL = "https://api-open.data.gov.sg/v2/real-time/api/four-day-outlook"
CONFIG_KEYS = ("EVIDENCE_PIPELINE_V3", "EVIDENCE_RETRIEVAL_MODE", "EVIDENCE_ASSESSMENT_MODE",
               "OLLAMA_ASSESSMENT_MODEL", "POOL_SETTLES_THRESHOLD", "POOL_SETTLES_THRESHOLD_JEV", "POOL_SETTLES_THRESHOLD_OSS")
SECRET_KEYS = ("JEV_API_KEY", "OLLAMA_API_KEY", "TAVILY_API_KEY", "GOOGLE_FACT_CHECK_API_KEY")


def run(backend, branch, credentials, payload):
    sys.path.insert(0, str(backend))
    from dotenv import load_dotenv
    # Shell state must not silently override the shared evaluation profile.
    for key in CONFIG_KEYS + SECRET_KEYS:
        os.environ.pop(key, None)
    load_dotenv(credentials, override=True)
    for key in SECRET_KEYS:
        os.environ.setdefault(key, "")
    for key in ("POOL_SETTLES_THRESHOLD", "POOL_SETTLES_THRESHOLD_JEV", "POOL_SETTLES_THRESHOLD_OSS"):
        os.environ.setdefault(key, "")
    os.environ.setdefault("OLLAMA_ASSESSMENT_MODEL", "gpt-oss:120b")
    os.environ.update(EVIDENCE_PIPELINE_V3="1" if branch == "experimental" else "0",
                      EVIDENCE_RETRIEVAL_MODE="web", EVIDENCE_ASSESSMENT_MODE="semantic")
    import httpx
    requests = []
    original_send = httpx.AsyncClient.send
    fixture = payload.get("forecast_fixture")

    async def instrumented_send(client, request, **kwargs):
        started = time.perf_counter()
        event = {"host": request.url.host, "method": request.method}
        requests.append(event)
        try:
            if fixture and str(request.url) == FORECAST_URL:
                event["replayed_forecast"] = True
                response = httpx.Response(200, json=fixture["payload"], request=request)
            else:
                response = await original_send(client, request, **kwargs)
            event["status"] = response.status_code
            if request.url.host in {"ollama.com", "api.typesafe.ai"}:
                try:
                    body = response.json()
                    usage = body.get("usage", {})
                    # Only numerical counters, never provider response text/request bodies.
                    counters = {k: v for k, v in usage.items() if isinstance(v, (int, float))} if isinstance(usage, dict) else {}
                    for key in ("prompt_eval_count", "eval_count"):
                        if type(body.get(key)) is int:
                            counters[key] = body[key]
                    if counters:
                        event["reported_usage"] = counters
                except (ValueError, AttributeError, httpx.ResponseNotRead):
                    pass
            return response
        except Exception as error:
            event["error_type"] = type(error).__name__
            raise
        finally:
            event["seconds"] = round(time.perf_counter() - started, 3)

    httpx.AsyncClient.send = instrumented_send
    captured = {}
    result = {}
    try:
        from app.pipeline.orchestration.dependencies import get_pipeline_orchestrator
        from app.pipeline.orchestration.repository import InMemoryResultRepository
        from app.pipeline.orchestration.service import PipelineOrchestrator
        runtime = get_pipeline_orchestrator()
        def capture(name, function):
            def wrapped(*args):
                value = function(*args)
                captured[name] = value.model_dump(mode="json")
                return value
            return wrapped
        pipeline = PipelineOrchestrator(
            prepare_input=runtime._prepare_input,
            analyze_claim=capture("claim_analysis", runtime._analyze_claim),
            retrieve_evidence=capture("retrieval", runtime._retrieve_evidence),
            assess_evidence=runtime._assess_evidence,
            repository=InMemoryResultRepository(),
            clock=lambda: datetime.fromisoformat(payload["assessed_at"]),
            pipeline_version=runtime._pipeline_version)
        if payload.get("preflight"):
            required = ["OLLAMA_API_KEY", "TAVILY_API_KEY"] + (["JEV_API_KEY"] if branch == "experimental" else [])
            missing = [key for key in required if not os.environ.get(key)]
            result = {"ready": not missing, "missing_credentials": missing, "pipeline_version": runtime._pipeline_version}
            value = None
        else:
            value = pipeline.analyze(payload["claim"]).model_dump(mode="json")
        # Import by file to avoid adding the experimental backend to sys.path.
        import importlib.util
        spec = importlib.util.spec_from_file_location("evaluation_compare", Path(__file__).with_name("compare.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if value is not None:
            result = {"result": value, "outcome": module.outcome(value)}
    except Exception as error:
        result = {"error_code": getattr(error, "error_code", type(error).__name__),
                  "stage": getattr(error, "stage", None)}
    finally:
        httpx.AsyncClient.send = original_send
    result.update(captured)
    result["requests"] = requests
    result["effective_config"] = {k: os.environ.get(k, "<code default>") for k in CONFIG_KEYS}
    result["credentials_present"] = {k: bool(os.environ.get(k)) for k in SECRET_KEYS}
    result["python_version"] = sys.version.split()[0]
    result["packages"] = {name: importlib.metadata.version(name) for name in ("httpx", "pydantic", "python-dotenv")}
    text = json.dumps(result, ensure_ascii=False)
    for key, value in os.environ.items():
        if any(word in key.upper() for word in ("API_KEY", "TOKEN", "PASSWORD", "SECRET")) and len(value) >= 8:
            text = text.replace(value, "[REDACTED]")
    return text


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", type=Path, required=True)
    parser.add_argument("--branch", choices=["original", "experimental"], required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    args = parser.parse_args()
    payload = json.load(sys.stdin)
    with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        try:
            output = run(args.backend, args.branch, args.credentials, payload)
        except Exception as error:
            output = json.dumps({"error_code": type(error).__name__})
    print(output)
