"""Explicitly enabled prototype checkout. No payment provider or card data."""
import os
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from app.accounts.models import UserProfile
from app.accounts.repository import _new_premium_allowance, _profile_view
from app.analyses.store import active_profile, reject


class DemoPaymentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_demo: Literal[True]


class DemoPaymentResult(BaseModel):
    mode: Literal["demo"] = "demo"
    status: Literal["upgraded", "already_premium"]
    amount_charged: int = 0
    receipt_id: str | None = None
    profile: UserProfile


def demo_offer():
    return {"enabled": os.environ.get("DEMO_PAYMENTS_ENABLED", "0").lower() in {"1", "true", "yes"},
            "mode": "demo", "currency": "SGD", "display_price_cents": 2000,
            "amount_charged": 0, "monthly_checks": 60}


def complete_demo_payment(store, uid):
    if not demo_offer()["enabled"]:
        reject(503, "DEMO_PAYMENTS_DISABLED", "Demo payments are not enabled on this server.")
    now = store.clock()
    # One receipt per account makes retries (including lost responses) harmless.
    receipt_id = "demo_" + uuid4().hex

    def upgrade(tx):
        profile = active_profile(tx.get("users", uid))
        allowance = tx.get("usage_allowances", uid)
        receipt = tx.get("demo_payments", uid)
        lock = tx.get("analysis_locks", uid)
        deletion = tx.get("account_deletions", uid)
        if deletion:
            reject(403, "ACCOUNT_UNAVAILABLE", "This account is currently unavailable.")
        if profile.get("role") == "premium":
            return DemoPaymentResult(status="already_premium", receipt_id=(receipt or {}).get("receipt_id"),
                                     profile=_profile_view(profile, allowance, now))
        if profile.get("role") != "free":
            reject(403, "UPGRADE_UNAVAILABLE", "Only Free app accounts can use demo checkout.")
        if receipt:
            reject(409, "DEMO_UPGRADE_USED", "This account has already used its demo upgrade. Contact the project team.")
        if lock and lock.get("expires_at", now) > now:
            reject(409, "ANALYSIS_IN_PROGRESS", "Wait for your current check to finish before upgrading.")
        profile = {**profile, "role": "premium", "account_type": "app", "updated_at": now}
        allowance = _new_premium_allowance(uid, now)
        tx.set("users", uid, profile)
        tx.set("usage_allowances", uid, allowance)
        tx.set("demo_payments", uid, {"user_id": uid, "receipt_id": receipt_id,
               "mode": "demo", "status": "completed", "currency": "SGD", "amount_charged": 0,
               "previous_role": "free", "new_role": "premium", "created_at": now})
        return DemoPaymentResult(status="upgraded", receipt_id=receipt_id,
                                 profile=_profile_view(profile, allowance, now))

    return store.run(upgrade)
