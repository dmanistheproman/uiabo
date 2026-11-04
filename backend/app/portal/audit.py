"""Durable access/action audit, without request content, tokens or query strings."""
from datetime import datetime, timezone
from hashlib import sha256
from uuid import uuid4
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from app.firebase import get_firestore_client


class AuditStore:
    def write(self, key, value):
        get_firestore_client().collection("operational_audit").document(key).set(value, merge=True)


def get_audit_store():
    return AuditStore()


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if not request.url.path.startswith(("/portal/", "/admin/")) or request.method == "OPTIONS":
            return await call_next(request)
        factory = request.app.dependency_overrides.get(get_audit_store, get_audit_store)
        store = factory()
        key = uuid4().hex
        request.state.audit_id = key
        parts = request.url.path.split("/")
        target_mask = None
        if len(parts) > 3 and parts[1:3] == ["admin", "users"]:
            target_mask = sha256(parts[3].encode()).hexdigest()[:16]
            parts[3] = "{user_id}"
        event = {"method": request.method, "path": "/".join(parts)[:300], "target_mask": target_mask,
                 "started_at": datetime.now(timezone.utc), "outcome": "started"}
        try:
            await run_in_threadpool(store.write, key, event)
        except Exception:
            return JSONResponse({"detail": {"error_code": "AUDIT_UNAVAILABLE",
                "message": "Operational services are temporarily unavailable. Please retry."}}, status_code=503)
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            uid = getattr(request.state, "authenticated_uid", None)
            event.update(finished_at=datetime.now(timezone.utc), status_code=status,
                         outcome="succeeded" if status < 400 else "denied" if status in {401,403} else "failed",
                         actor_mask=sha256(uid.encode()).hexdigest()[:16] if uid else None)
            metadata = getattr(request.state, "audit_metadata", None)
            operational_role = getattr(request.state, "operational_role", None)
            if operational_role:
                event["actor_role"] = operational_role
            target_uid = getattr(request.state, "audit_target_uid", None)
            if target_uid:
                event["target_mask"] = sha256(target_uid.encode()).hexdigest()[:16]
            if metadata:
                event["action_details"] = metadata
            try:
                await run_in_threadpool(store.write, key, event)
            except Exception:
                # The durable started event remains for reconciliation; do not
                # make a completed mutation look unsuccessful and invite retries.
                import logging
                logging.getLogger(__name__).error("Audit outcome pending: %s", key)
