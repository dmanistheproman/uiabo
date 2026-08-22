"""Persistence adapters for completed and failed analysis runs."""

from typing import Any, Protocol

from firebase_admin import firestore

from app.firebase import get_firestore_client
from app.pipeline.shared.errors import PipelinePersistenceError
from app.pipeline.shared.models import (
    FailedAnalysisRecord,
    TextAnalysisResult,
)


RESULTS_COLLECTION = "analysis_results"


class ResultRepository(Protocol):
    """Storage contract used by the orchestrator."""

    def save_result(self, result: TextAnalysisResult) -> None:
        """Persist a completed analysis result."""

    def save_failure(self, failure: FailedAnalysisRecord) -> None:
        """Persist a failed analysis run for investigation."""


class FirestoreResultRepository:
    """Store analysis records in Cloud Firestore.

    The Firestore client is loaded lazily so importing the API does not require
    credentials. Tests can inject a fake client without contacting Firebase.
    """

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = get_firestore_client()
        return self._client

    def save_result(self, result: TextAnalysisResult) -> None:
        self._save(result.result_id, result)

    def save_failure(self, failure: FailedAnalysisRecord) -> None:
        self._save(failure.result_id, failure)

    def _save(
        self,
        result_id: str,
        record: TextAnalysisResult | FailedAnalysisRecord,
    ) -> None:
        payload = record.model_dump(mode="json")

        # Firestore should receive the real datetime for querying/sorting. The
        # rest of the JSON-compatible payload is portable and inspectable.
        payload["created_at"] = record.created_at
        payload["saved_at"] = firestore.SERVER_TIMESTAMP

        try:
            (
                self.client.collection(RESULTS_COLLECTION)
                .document(result_id)
                .set(payload)
            )
        except Exception as error:
            raise PipelinePersistenceError(
                "The analysis result could not be saved."
            ) from error


class InMemoryResultRepository:
    """Small repository used by tests and local integration examples."""

    def __init__(self) -> None:
        self.results: dict[str, TextAnalysisResult] = {}
        self.failures: dict[str, FailedAnalysisRecord] = {}

    def save_result(self, result: TextAnalysisResult) -> None:
        self.results[result.result_id] = result

    def save_failure(self, failure: FailedAnalysisRecord) -> None:
        self.failures[failure.result_id] = failure

