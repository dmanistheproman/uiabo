"""Durable, resumable self-deletion. No user data is removed by a GET request."""
from datetime import datetime, timedelta, timezone
import os
from hashlib import sha256
from firebase_admin import auth
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from fastapi import HTTPException
from app.firebase import get_firestore_client, get_firebase_app
from app.analyses.images import get_image_storage, image_prefix
from app.accounts.roles import stored_account_type


def deny(code, message, status=409):
    raise HTTPException(status, detail={"error_code": code, "message": message})


class DeletionService:
    def __init__(self, client=None, clock=None):
        self._client = client
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def client(self):
        return self._client if self._client is not None else get_firestore_client()

    def request(self, user):
        now = self.clock()
        if user.auth_time is None or not 0 <= now.timestamp() - user.auth_time <= 300:
            deny("RECENT_LOGIN_REQUIRED", "Sign in again before deleting your account.", 401)
        profile_ref = self.client.collection("users").document(user.uid)
        job_ref = self.client.collection("account_deletions").document(user.uid)

        @firestore.transactional
        def start(tx):
            profile = profile_ref.get(transaction=tx).to_dict()
            job = job_ref.get(transaction=tx).to_dict()
            lock = self.client.collection("analysis_locks").document(user.uid).get(transaction=tx).to_dict()
            if job:
                return {"status": "pending", "message": "Account deletion has already been requested."}
            if not profile or stored_account_type(profile) != "app" or profile.get("role") not in {"free", "premium"}:
                deny("DELETION_UNAVAILABLE", "Self-deletion is available to app accounts only.", 403)
            if lock and lock.get("expires_at", now) > now:
                deny("ANALYSIS_IN_PROGRESS", "Wait for your current check to finish before deleting your account.")
            # Deactivation blocks new writes; a grace period lets requests already
            # admitted before this transaction finish before the final sweep.
            tx.update(profile_ref, {"account_status": "deactivated", "updated_at": now})
            tx.set(job_ref, {"status": "pending", "requested_at": now,
                             "not_before": now + timedelta(minutes=5)})
            return {"status": "pending", "message": "Your account is unavailable while its data is being deleted."}
        return start(self.client.transaction())

    def _owned(self, collection, uid):
        return self.client.collection(collection).where(filter=FieldFilter("user_id", "==", uid)).stream()

    def cleanup(self, uid):
        # Authentication is disabled first, but only after a durable job exists.
        # Every following step tolerates already-removed data on a retry.
        try:
            auth.update_user(uid, disabled=True, app=get_firebase_app())
            auth.revoke_refresh_tokens(uid, app=get_firebase_app())
        except auth.UserNotFoundError:
            pass
        results = list(self._owned("analysis_results", uid))
        has_images = any((item.to_dict() or {}).get("saved_image") for item in results)
        if has_images or os.getenv("FIREBASE_STORAGE_BUCKET", "").strip():
            images = get_image_storage()
            prefix = image_prefix(uid, "").rstrip("/") + "/"
            for blob in images.bucket.list_blobs(prefix=prefix, timeout=30):
                from google.api_core.exceptions import NotFound
                try:
                    blob.delete(if_generation_match=blob.generation, timeout=30)
                except NotFound:
                    pass
        for result in results:
            self.client.collection("pipeline_runs").document(result.id).delete()
            result.reference.delete()
        # Reports/feedback contain free-form personal content, so remove the
        # complete owned record, including its investigation history.
        for collection in ("result_reports", "feedback"):
            for item in self._owned(collection, uid):
                item.reference.delete()
        for collection in ("usage_allowances", "analysis_locks", "demo_payments"):
            self.client.collection(collection).document(uid).delete()
        self.client.collection("deleted_account_receipts").document(sha256(uid.encode()).hexdigest()).set({"deleted_at": self.clock()})
        try:
            auth.delete_user(uid, app=get_firebase_app())
        except auth.UserNotFoundError:
            pass
        self.client.collection("users").document(uid).delete()
        self.client.collection("account_deletions").document(uid).delete()

    def run_pending(self):
        now = self.clock()
        for job in self.client.collection("account_deletions").stream():
            data = job.to_dict() or {}
            if data.get("not_before", now) > now:
                continue
            try:
                self.cleanup(job.id)
            except Exception:
                # No raw provider errors or user content in the job record.
                job.reference.set({"status": "retry_pending", "last_attempt_at": now,
                                   "not_before": now + timedelta(minutes=1)}, merge=True)


def get_deletion_service():
    return DeletionService()
