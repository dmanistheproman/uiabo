"""Bounded, read-only operational audit history for administrators."""
import base64
import json
import re
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any
from pydantic import BaseModel, Field
from fastapi import HTTPException
from google.cloud.firestore_v1.base_query import FieldFilter
from app.firebase import get_firestore_client


ACTIONS = ("provision_account", "change_roles", "convert_staff_to_app", "change_status", "review_feedback",
           "investigate_report", "monitor_pipeline", "portal_login", "view_audit", "view_accounts", "view_feedback", "other")


def event_action(event):
    path, method = event.get("path", ""), event.get("method", "GET")
    if path == "/admin/provision": return "provision_account"
    if path.endswith("/convert-to-app") and path.startswith("/admin/users/"): return "convert_staff_to_app"
    if path.endswith("/roles"): return "change_roles"
    if path.endswith("/status") and path.startswith("/admin/users/"): return "change_status"
    if path.startswith("/admin/feedback/") and method == "PATCH": return "review_feedback"
    if path.startswith("/portal/reports"): return "investigate_report"
    if path.startswith(("/portal/runs", "/portal/ingestion")): return "monitor_pipeline"
    if path == "/portal/session": return "portal_login"
    if path == "/admin/audit": return "view_audit"
    if path.startswith("/admin/users"): return "view_accounts"
    if path.startswith("/admin/feedback"): return "view_feedback"
    return "other"


class AuditEvent(BaseModel):
    event_id: str
    action: str
    started_at: datetime
    finished_at: datetime | None = None
    outcome: str
    actor_mask: str | None = None
    actor_name: str | None = None
    actor_email: str | None = None
    actor_role: str | None = None
    target_mask: str | None = None
    target_name: str | None = None
    target_email: str | None = None
    method: str
    path: str
    status_code: int | None = None
    change_applied: bool = False
    action_details: dict[str, Any] = Field(default_factory=dict)


class AuditPage(BaseModel):
    items: list[AuditEvent]
    next_cursor: str | None = None
    scanned: int


def audit_window(from_time, to_time, now=None):
    now = now or datetime.now(timezone.utc)
    to_time = to_time or now
    from_time = from_time or to_time - timedelta(days=7)
    if from_time.tzinfo is None or to_time.tzinfo is None or from_time > to_time or to_time - from_time > timedelta(days=31):
        raise HTTPException(422, detail={"error_code": "INVALID_AUDIT_RANGE",
            "message": "Choose a valid date range of up to 31 days, including a timezone."})
    return from_time, to_time


def matches(event, *, action=None, outcome=None, user_id=None):
    mask = sha256(user_id.encode()).hexdigest()[:16] if user_id else None
    return ((not action or event_action(event) == action)
            and (not outcome or event.get("outcome") == outcome)
            and (not mask or mask in {event.get("actor_mask"), event.get("target_mask")}))


def public_event(key, event, accounts):
    permitted = set(AuditEvent.model_fields) - {"event_id", "action", "action_details", "actor_name", "actor_email", "target_name", "target_email"}
    data = {field: value for field, value in event.items() if field in permitted}
    details = event.get("action_details") or {}
    data["action_details"] = {k: details[k] for k in ("reason", "before", "after", "account_status", "account_type_from", "account_type_to", "membership") if k in details}
    for prefix in ("actor", "target"):
        account = accounts.get(event.get(f"{prefix}_mask"), {})
        data[f"{prefix}_name"] = account.get("name")
        data[f"{prefix}_email"] = account.get("email")
    return AuditEvent(event_id=key, action=event_action(event), **data)


def decode_cursor(cursor):
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        if set(data) != {"id", "at"} or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", data["id"]):
            raise ValueError()
        at = datetime.fromisoformat(data["at"])
        if at.tzinfo is None: raise ValueError()
        return data["id"], at
    except Exception:
        raise HTTPException(422, detail={"error_code": "INVALID_AUDIT_CURSOR", "message": "Reload audit history to continue."}) from None


def encode_cursor(snapshot):
    return base64.urlsafe_b64encode(json.dumps({"id": snapshot.id,
        "at": snapshot.to_dict()["started_at"].isoformat()}).encode()).decode()


class AuditHistory:
    def __init__(self, client=None):
        self.client = client or get_firestore_client()

    def list_events(self, *, from_time, to_time, action=None, outcome=None, user_id=None, cursor=None, limit=50):
        collection = self.client.collection("operational_audit")
        query = (collection.where(filter=FieldFilter("started_at", ">=", from_time))
            .where(filter=FieldFilter("started_at", "<=", to_time))
            .order_by("started_at", direction="DESCENDING").order_by("__name__", direction="DESCENDING"))
        if cursor:
            key, at = decode_cursor(cursor)
            query = query.start_after({"started_at": at, "__name__": collection.document(key)})
        # Filtering a bounded page in Python needs no composite Firestore indexes.
        # The continuation follows the last scanned record, including unmatched rows.
        snapshots = list(query.limit(301).stream())
        chosen, scanned, last = [], 0, None
        for snapshot in snapshots[:300]:
            scanned += 1
            last = snapshot
            if matches(snapshot.to_dict(), action=action, outcome=outcome, user_id=user_id):
                chosen.append(snapshot)
            if len(chosen) == limit: break
        next_cursor = encode_cursor(last) if last and len(snapshots) > scanned else None
        masks = {s.to_dict().get(field) for s in chosen for field in ("actor_mask", "target_mask")} - {None}
        accounts = {}
        if masks:
            # Resolve current account names without retaining personal details in
            # historical audit documents after account deletion.
            for snapshot in self.client.collection("users").select(["uid", "name", "email"]).stream():
                account = snapshot.to_dict()
                mask = sha256(snapshot.id.encode()).hexdigest()[:16]
                if mask in masks: accounts[mask] = account
                if len(accounts) == len(masks): break
        return AuditPage(items=[public_event(s.id, s.to_dict(), accounts) for s in chosen],
                         next_cursor=next_cursor, scanned=scanned)


def get_audit_history():
    return AuditHistory()
