"""Tests for Firestore persistence without contacting Firebase."""

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from app.pipeline.orchestration.repository import (
    RESULTS_COLLECTION,
    FirestoreResultRepository,
)
from app.pipeline.shared.errors import PipelinePersistenceError
from app.pipeline.shared.models import EvidenceProvenance, TextAnalysisResult


FIXTURE = (
    Path(__file__).parents[2]
    / "fixtures"
    / "sprint_1"
    / "text_analysis_result.json"
)


class FakeDocument:
    def __init__(self, document_id: str, *, should_fail: bool = False) -> None:
        self.document_id = document_id
        self.should_fail = should_fail
        self.payload = None

    def set(self, payload: dict) -> None:
        if self.should_fail:
            raise RuntimeError("Firestore unavailable")
        self.payload = payload


class FakeCollection:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.documents: dict[str, FakeDocument] = {}

    def document(self, document_id: str) -> FakeDocument:
        document = FakeDocument(
            document_id,
            should_fail=self.should_fail,
        )
        self.documents[document_id] = document
        return document


class FakeFirestoreClient:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.collection_name = None
        self.collection_value = FakeCollection(should_fail=should_fail)

    def collection(self, name: str) -> FakeCollection:
        self.collection_name = name
        return self.collection_value


def _result() -> TextAnalysisResult:
    with FIXTURE.open(encoding="utf-8") as handle:
        return TextAnalysisResult.model_validate(json.load(handle))


def test_firestore_repository_writes_complete_record() -> None:
    client = FakeFirestoreClient()
    repository = FirestoreResultRepository(client=client)
    result = _result()

    repository.save_result(result)

    assert client.collection_name == RESULTS_COLLECTION
    document = client.collection_value.documents[result.result_id]
    assert document.document_id == result.result_id
    assert document.payload["processing_status"] == "completed"
    assert document.payload["evidence"][0]["stance"] == "contradicting"
    assert document.payload["created_at"] == datetime(
        2026,
        8,
        20,
        10,
        0,
        5,
        tzinfo=timezone.utc,
    )
    assert "saved_at" in document.payload


def test_firestore_failure_becomes_controlled_error() -> None:
    repository = FirestoreResultRepository(
        client=FakeFirestoreClient(should_fail=True)
    )

    with pytest.raises(PipelinePersistenceError) as raised:
        repository.save_result(_result())

    assert raised.value.error_code == "RESULT_STORAGE_FAILED"
    assert raised.value.http_status == 503


def test_new_source_provenance_survives_firestore_serialisation() -> None:
    client = FakeFirestoreClient()
    result = _result()
    item = result.evidence[0]
    item.provenance = EvidenceProvenance(source_policy="catalogue", source_reason="Reviewed publisher.",
        origin_group="gov.sg", discovery_method="web_search", relevance="direct",
        relevance_reason="The source addresses the claim.", relevance_quote=item.passage,
        applicability="established", applicability_reason="Same subject and conditions.")
    FirestoreResultRepository(client=client).save_result(result)
    payload = dict(client.collection_value.documents[result.result_id].payload)
    payload.pop("saved_at")
    restored = TextAnalysisResult.model_validate(payload)
    assert restored.evidence[0].provenance == item.provenance
