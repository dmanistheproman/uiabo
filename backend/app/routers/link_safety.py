"""Authenticated URL checks using the same atomic history/allowance policy as text."""

import time
from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException

from app.link_safety.models import FailedLinkSafetyRecord, LinkSafetyRequest, LinkSafetyResult
from app.link_safety.service import LinkSafetyError, WebRiskClient, get_web_risk_client, validate_url
from app.pipeline.orchestration.run_recorder import RunStore, get_run_store
from app.routers.analysis import Store, User, unavailable


router = APIRouter(prefix="/analysis", tags=["Link safety"])


@router.post("/link-safety", response_model=LinkSafetyResult)
def check_link(request: LinkSafetyRequest, user: User, store: Store,
               provider: Annotated[WebRiskClient, Depends(get_web_risk_client)],
               runs: Annotated[RunStore, Depends(get_run_store)],
               idempotency_key: Annotated[str | None, Header(max_length=64, pattern=r"^[a-zA-Z0-9-]+$")] = None):
    reservation = None
    try:
        checked_url = validate_url(request.url)
        reservation = store.reserve(user.uid, idempotency_key or str(uuid4()), request.url,
                                    input_type="link_safety")
        if "existing" in reservation:
            existing = reservation["existing"]
            if existing["processing_status"] == "completed":
                return existing
            raise HTTPException(409, detail={"error_code": "PREVIOUS_CHECK_FAILED",
                "message": "The previous link check failed. Start a new check to retry."})
        started = time.perf_counter()
        try:
            result = provider.lookup(request.url, checked_url, reservation["result_id"])
        except LinkSafetyError as error:
            store.finish(user.uid, reservation, FailedLinkSafetyRecord(
                result_id=reservation["result_id"], submitted_url=request.url, checked_url=checked_url,
                error_code=error.code, message=error.message, created_at=datetime.now(timezone.utc)))
            _record_link_run(runs, reservation["result_id"], "failed",
                             started, error_code=error.code, message=error.message)
            raise
        _record_link_run(runs, reservation["result_id"], "completed", started)
        return store.finish(user.uid, reservation, result)
    except LinkSafetyError as error:
        raise HTTPException(error.status, detail={"error_code": error.code, "message": error.message}) from None
    except HTTPException:
        raise
    except Exception:
        raise unavailable() from None
    finally:
        if reservation and "token" in reservation:
            try:
                store.release(user.uid, reservation)
            except Exception:
                pass  # Bounded lease permits recovery after a storage outage.


def _record_link_run(runs: RunStore, result_id: str, status: str,
                     started: float, error_code: str | None = None, message: str | None = None):
    """Monitoring is best-effort; a failed record write never fails a check."""
    try:
        runs.record({
            "run_id": result_id, "input_type": "link_safety", "status": status,
            "created_at": datetime.now(timezone.utc),
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "stage_timings_ms": {},
            **({"failure_stage": "link_safety", "error_code": error_code, "message": message}
               if status == "failed" else {}),
            "pipeline_version": "link-safety-v1",
        })
    except Exception:
        return
