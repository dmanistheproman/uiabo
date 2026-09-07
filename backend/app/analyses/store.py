"""User-owned history and atomic allowance charging for successful analyses."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from hashlib import sha256
from threading import RLock
from uuid import uuid4

from fastapi import HTTPException
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from app.accounts.repository import _new_free_allowance, _new_premium_allowance
from app.firebase import get_firestore_client
from app.pipeline.shared.models import FailedAnalysisRecord, TextAnalysisResult


LEASE_SECONDS = 300


def reject(status, code, message):
    raise HTTPException(status, detail={"error_code": code, "message": message})


def active_profile(profile):
    if not profile:
        reject(404, "PROFILE_NOT_FOUND", "Finish setting up your profile to continue.")
    if profile.get("account_status") != "active":
        reject(403, "ACCOUNT_UNAVAILABLE", "This account is currently unavailable.")
    return profile


def current_allowance(uid, profile, allowance, now):
    if profile["role"] == "free":
        if not allowance or allowance["reset_at"] <= now or allowance.get("tier") != "free":
            return _new_free_allowance(uid, now)
        return dict(allowance)
    # Only the server-managed role grants entitlement; clients cannot set it.
    if profile["role"] != "premium":
        reject(403, "ALLOWANCE_UNAVAILABLE", "Your submission allowance is unavailable. Please contact support.")
    if not allowance or allowance["reset_at"] <= now or allowance.get("tier") != "premium":
        return _new_premium_allowance(uid, now)
    return dict(allowance)


def public_record(record):
    fields = (TextAnalysisResult.model_fields if record.get("processing_status") == "completed"
              else FailedAnalysisRecord.model_fields)
    return {key: record[key] for key in fields if key in record}


class AnalysisStore:
    """Shared policy; concrete stores provide atomic run() and history queries."""

    def __init__(self, clock=None):
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def reserve(self, uid, request_key, text):
        now = self.clock()
        result_id = sha256(f"{uid}:{request_key}".encode()).hexdigest()[:32]
        fingerprint = sha256(text.encode()).hexdigest()
        token = str(uuid4())
        def operation(tx):
            profile = active_profile(tx.get("users", uid))
            existing = tx.get("analysis_results", result_id)
            allowance = tx.get("usage_allowances", uid)
            lock = tx.get("analysis_locks", uid)
            if existing:
                if existing.get("user_id") != uid or existing.get("request_fingerprint") != fingerprint:
                    reject(409, "REQUEST_KEY_REUSED", "Start a new check when changing the text.")
                return {"result_id": result_id, "existing": public_record(existing)}
            if lock and lock["expires_at"] > now:
                reject(409, "ANALYSIS_IN_PROGRESS", "A check is already running. Please wait, then open Results.")
            allowance = current_allowance(uid, profile, allowance, now)
            if allowance["remaining_submissions"] <= 0:
                reject(429, "ALLOWANCE_EXHAUSTED", "You have used your allowance. Please wait until it resets.")
            tx.set("usage_allowances", uid, allowance)
            tx.set("analysis_locks", uid, {"token": token, "result_id": result_id,
                "expires_at": now + timedelta(seconds=LEASE_SECONDS)})
            return {"result_id": result_id, "token": token, "fingerprint": fingerprint}
        return self.run(operation)

    def finish(self, uid, reservation, record):
        now = self.clock()
        payload = record.model_dump(mode="json")
        payload.update(result_id=reservation["result_id"], user_id=uid, input_type="text",
                       request_fingerprint=reservation["fingerprint"], created_at=now,
                       saved_at=now, share_enabled=False)
        def operation(tx):
            profile = active_profile(tx.get("users", uid))
            lock = tx.get("analysis_locks", uid)
            existing = tx.get("analysis_results", reservation["result_id"])
            allowance = tx.get("usage_allowances", uid)
            if existing:
                return public_record(existing)
            if not lock or lock.get("token") != reservation["token"]:
                reject(409, "ANALYSIS_EXPIRED", "This check expired. Please try again.")
            if record.processing_status == "completed":
                allowance = current_allowance(uid, profile, allowance, now)
                if allowance["remaining_submissions"] <= 0:
                    reject(429, "ALLOWANCE_EXHAUSTED", "Your allowance has been used. Please wait until it resets.")
                allowance["successful_submissions"] += 1
                allowance["remaining_submissions"] -= 1
                allowance["updated_at"] = now
                tx.set("usage_allowances", uid, allowance)
            tx.set("analysis_results", reservation["result_id"], payload)
            tx.delete("analysis_locks", uid)
            return public_record(payload)
        return self.run(operation)

    def release(self, uid, reservation):
        def operation(tx):
            lock = tx.get("analysis_locks", uid)
            if lock and lock.get("token") == reservation.get("token"):
                tx.delete("analysis_locks", uid)
        self.run(operation)

    def get_owned(self, uid, result_id):
        def operation(tx):
            active_profile(tx.get("users", uid))
            record = tx.get("analysis_results", result_id)
            if not record or record.get("user_id") != uid:
                reject(404, "RESULT_NOT_FOUND", "This result could not be found.")
            return public_record(record)
        return self.run(operation)


class FirestoreSession:
    def __init__(self, client, transaction):
        self.client, self.transaction = client, transaction

    def get(self, collection, document):
        snapshot = self.client.collection(collection).document(document).get(transaction=self.transaction)
        return snapshot.to_dict() if snapshot.exists else None

    def set(self, collection, document, value):
        self.transaction.set(self.client.collection(collection).document(document), value)

    def delete(self, collection, document):
        self.transaction.delete(self.client.collection(collection).document(document))


class FirestoreAnalysisStore(AnalysisStore):
    def __init__(self, client=None, clock=None):
        super().__init__(clock)
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = get_firestore_client()
        return self._client

    def run(self, operation):
        @firestore.transactional
        def execute(transaction):
            return operation(FirestoreSession(self.client, transaction))
        return execute(self.client.transaction())

    def history(self, uid, limit=20, cursor=None):
        active_profile(self.client.collection("users").document(uid).get().to_dict())
        # Single-field owner query works with the existing project permissions.
        # Sort the user's complete (small prototype) history, then paginate. A
        # composite-index query can replace this when index-admin access exists.
        query = self.client.collection("analysis_results").where(filter=FieldFilter("user_id", "==", uid))
        records = [item.to_dict() for item in query.stream()]
        records.sort(key=lambda data: (data["created_at"], data["result_id"]), reverse=True)
        if cursor:
            index = next((i for i, data in enumerate(records) if data["result_id"] == cursor), None)
            if index is None:
                reject(404, "RESULT_NOT_FOUND", "This result could not be found.")
            records = records[index + 1:]
        return {"results": [public_record(item) for item in records[:limit]],
                "next_cursor": records[limit - 1]["result_id"] if len(records) > limit else None}


class MemorySession:
    def __init__(self, documents):
        self.documents = documents
    def get(self, collection, document):
        return deepcopy(self.documents.get((collection, document)))
    def set(self, collection, document, value):
        self.documents[collection, document] = deepcopy(value)
    def delete(self, collection, document):
        self.documents.pop((collection, document), None)


class InMemoryAnalysisStore(AnalysisStore):
    def __init__(self, clock=None):
        super().__init__(clock)
        self.documents, self.lock = {}, RLock()
    def run(self, operation):
        with self.lock:
            copied = deepcopy(self.documents)
            result = operation(MemorySession(copied))
            self.documents = copied
            return result
    def history(self, uid, limit=20, cursor=None):
        active_profile(self.documents.get(("users", uid)))
        items = [data for (collection, _), data in self.documents.items()
                 if collection == "analysis_results" and data.get("user_id") == uid]
        items.sort(key=lambda data: (data["created_at"], data["result_id"]), reverse=True)
        if cursor:
            self.get_owned(uid, cursor)
            items = items[next(i for i, data in enumerate(items) if data["result_id"] == cursor) + 1:]
        return {"results": [public_record(data) for data in items[:limit]],
                "next_cursor": items[limit - 1]["result_id"] if len(items) > limit else None}


@lru_cache
def get_analysis_store():
    return FirestoreAnalysisStore()
