"""Pure helpers shared by the report submission and portal routes."""

from datetime import datetime
from hashlib import sha256
from typing import Any
from uuid import uuid4

from app.portal.models import ReportAuditEntry


def mask_identifier(value: str, prefix: str) -> str:
    """A stable non-reversible label for a uid shown in the portal."""
    return f"{prefix}_{sha256(value.encode()).hexdigest()[:10]}"


def build_report_document(
    *,
    user_id: str,
    result_id: str,
    reason: str,
    detail: str,
    record: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    """Create the stored report document from a completed result record."""
    report_id = f"rpt_{uuid4().hex[:16]}"
    user_mask = mask_identifier(user_id, "usr")
    created_entry = ReportAuditEntry(
        at=now,
        actor_mask=user_mask,
        actor_role="user",
        action="created",
    ).model_dump(mode="json")
    return {
        "report_id": report_id,
        "result_id": result_id,
        "user_id": user_id,
        "user_mask": user_mask,
        "input_type": record.get("input_type", "text"),
        "reason": reason,
        "detail": detail,
        "status": "open",
        "created_at": now,
        "updated_at": now,
        "snapshot": {
            "claim_category": record["claim_category"],
            "checkable": record["checkable"],
            "concern_label": record["concern_label"],
            "misinformation_risk_score": record.get("misinformation_risk_score"),
            "uncertainty": record["uncertainty"],
            "pipeline_version": record["pipeline_version"],
            "result_created_at": record["created_at"],
        },
        "review_note": None,
        "reviewed_by_mask": None,
        "reviewed_at": None,
        "history": [created_entry],
    }


def apply_report_update(
    document: dict[str, Any],
    *,
    status_change: str | None,
    note: str | None,
    actor_uid: str,
    actor_role: str,
    now: datetime,
) -> dict[str, Any]:
    """Apply a data engineer's update and append the audit trail (UC-42)."""
    updated = dict(document)
    entries: list[dict[str, Any]] = []
    actor_mask = mask_identifier(actor_uid, "de")

    if status_change is not None:
        entries.append({
            "at": now,
            "actor_mask": actor_mask,
            "actor_role": actor_role,
            "action": "status_changed",
            "status_from": document["status"],
            "status_to": status_change,
            "note": None,
        })
        updated["status"] = status_change

    if note is not None:
        entries.append({
            "at": now,
            "actor_mask": actor_mask,
            "actor_role": actor_role,
            "action": "note_added",
            "status_from": None,
            "status_to": None,
            "note": note,
        })
        updated["review_note"] = note
        updated["reviewed_by_mask"] = actor_mask

    if entries:
        updated["reviewed_at"] = now
        updated["updated_at"] = now
        updated["history"] = [*document.get("history", []), *entries]
    return updated
