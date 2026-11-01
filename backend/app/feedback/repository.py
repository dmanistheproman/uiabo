"""Firestore and in-memory repositories for user feedback."""

from collections.abc import Callable
from datetime import datetime, timezone
from functools import lru_cache
from typing import Protocol

from app.feedback.models import (
    FeedbackCategory,
    FeedbackRecord,
    FeedbackStatus,
)
from app.firebase import get_firestore_client


FEEDBACK_COLLECTION = "feedback"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FeedbackRepository(Protocol):
    def list_feedback(
        self,
        *,
        status: FeedbackStatus | None = None,
        category: FeedbackCategory | None = None,
        limit: int = 50,
    ) -> list[FeedbackRecord]:
        """Return feedback records for administrative review."""

    def get_feedback(
        self,
        feedback_id: str,
    ) -> FeedbackRecord | None:
        """Return one feedback record or None when it does not exist."""

    def save_feedback(
        self,
        record: FeedbackRecord,
    ) -> None:
        """Store a newly submitted feedback record."""

    def mark_reviewed(
        self,
        feedback_id: str,
        admin_uid: str,
    ) -> FeedbackRecord | None:
        """Mark one feedback record as reviewed by a System Administrator."""


class FirestoreFeedbackRepository:
    """Store and retrieve feedback records from Cloud Firestore."""

    def __init__(
        self,
        client=None,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._client = client or get_firestore_client()
        self._clock = clock

    def list_feedback(
        self,
        *,
        status: FeedbackStatus | None = None,
        category: FeedbackCategory | None = None,
        limit: int = 50,
    ) -> list[FeedbackRecord]:
        records: list[FeedbackRecord] = []

        snapshots = (
            self._client
            .collection(FEEDBACK_COLLECTION)
            .stream()
        )

        for snapshot in snapshots:
            data = snapshot.to_dict()

            if not data:
                continue

            if status is not None:
                if data.get("status") != status:
                    continue

            if category is not None:
                if data.get("category") != category:
                    continue

            records.append(
                FeedbackRecord.model_validate(data)
            )

        records.sort(
            key=lambda record: record.created_at,
            reverse=True,
        )

        return records[:limit]

    def get_feedback(
        self,
        feedback_id: str,
    ) -> FeedbackRecord | None:
        snapshot = (
            self._client
            .collection(FEEDBACK_COLLECTION)
            .document(feedback_id)
            .get()
        )

        if not snapshot.exists:
            return None

        data = snapshot.to_dict()

        if not data:
            return None

        return FeedbackRecord.model_validate(data)

    def save_feedback(
        self,
        record: FeedbackRecord,
    ) -> None:
        self._client.collection(FEEDBACK_COLLECTION).document(
            record.feedback_id
        ).set(record.model_dump(mode="json"))

    def mark_reviewed(
        self,
        feedback_id: str,
        admin_uid: str,
    ) -> FeedbackRecord | None:
        reference = (
            self._client
            .collection(FEEDBACK_COLLECTION)
            .document(feedback_id)
        )

        snapshot = reference.get()

        if not snapshot.exists:
            return None

        now = self._clock()

        reference.update(
            {
                "status": "reviewed",
                "reviewed_at": now,
                "reviewed_by": admin_uid,
            }
        )

        return self.get_feedback(feedback_id)


class InMemoryFeedbackRepository:
    """Deterministic feedback repository used by API tests."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._clock = clock

        self.feedback: dict[
            str,
            dict,
        ] = {}

    def list_feedback(
        self,
        *,
        status: FeedbackStatus | None = None,
        category: FeedbackCategory | None = None,
        limit: int = 50,
    ) -> list[FeedbackRecord]:
        records: list[FeedbackRecord] = []

        for data in self.feedback.values():
            if status is not None:
                if data.get("status") != status:
                    continue

            if category is not None:
                if data.get("category") != category:
                    continue

            records.append(
                FeedbackRecord.model_validate(data)
            )

        records.sort(
            key=lambda record: record.created_at,
            reverse=True,
        )

        return records[:limit]

    def get_feedback(
        self,
        feedback_id: str,
    ) -> FeedbackRecord | None:
        data = self.feedback.get(feedback_id)

        if data is None:
            return None

        return FeedbackRecord.model_validate(data)

    def save_feedback(
        self,
        record: FeedbackRecord,
    ) -> None:
        self.feedback[record.feedback_id] = record.model_dump(
            mode="json"
        )

    def mark_reviewed(
        self,
        feedback_id: str,
        admin_uid: str,
    ) -> FeedbackRecord | None:
        data = self.feedback.get(feedback_id)

        if data is None:
            return None

        data["status"] = "reviewed"
        data["reviewed_at"] = self._clock()
        data["reviewed_by"] = admin_uid

        return FeedbackRecord.model_validate(data)


@lru_cache
def get_feedback_repository() -> FeedbackRepository:
    return FirestoreFeedbackRepository()
