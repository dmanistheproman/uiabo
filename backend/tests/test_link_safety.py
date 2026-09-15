from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
import httpx
import pytest

from app.auth.models import AuthenticatedUser
from app.link_safety.service import LinkSafetyError, WebRiskClient, get_web_risk_client, validate_url
from app.main import app


NOW = datetime(2026, 9, 15, tzinfo=timezone.utc)
URL = "https://example.com/article?ref=message"
MATCH = {"threat": {"threatTypes": ["MALWARE", "SOCIAL_ENGINEERING"],
                     "expireTime": (NOW + timedelta(minutes=10)).isoformat()}}


def provider(payload=None, status=200, clock=lambda: NOW):
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(status, json={} if payload is None else payload)
    return WebRiskClient("test-key", transport=httpx.MockTransport(respond), clock=clock), requests


@pytest.mark.parametrize("url", [
    "", "example.com", "ftp://example.com", "file:///etc/passwd", "javascript:alert(1)",
    "http://localhost", "http://service.local", "http://127.0.0.1", "http://2130706433",
    "http://10.0.0.1", "http://169.254.169.254", "http://[::1]", "http://[fc00::1]",
    "https://user:password@example.com", "https://example.com\\@evil.com", "https://example.com/a\nb",
])
def test_invalid_or_private_urls_rejected(url):
    with pytest.raises(LinkSafetyError) as failure:
        validate_url(url)
    assert failure.value.code == "INVALID_LINK"


def test_public_urls_preserve_path_query_and_unicode_hostname():
    assert validate_url("  " + URL + "  ") == URL
    assert validate_url("https://bücher.de/page?q=x") == "https://xn--bcher-kva.de/page?q=x"
    assert validate_url("https://8.8.8.8/") == "https://8.8.8.8/"


def test_lookup_uses_only_google_endpoint_and_all_three_lists():
    service, requests = provider()
    result = service.lookup(URL, URL, "one")
    request = requests[0]
    assert request.url.host == "webrisk.googleapis.com"
    assert request.url.params["uri"] == URL
    assert set(request.url.params.get_list("threatTypes")) == {"MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE"}
    assert request.headers["X-Goog-Api-Key"] == "test-key"
    assert "test-key" not in str(request.url)
    assert result.safety_status == "no_known_threats" and result.threat_types == []
    assert "guarantee" in result.limitations


def test_positive_cache_reuses_until_expiry_and_preserves_original_check_time():
    now = NOW
    service, requests = provider(MATCH, clock=lambda: now)
    first = service.lookup(URL, URL, "one")
    now += timedelta(minutes=1)
    second = service.lookup(URL, URL, "two")
    assert first.safety_status == second.safety_status == "threat_detected"
    assert not first.cached and second.cached
    assert second.result_id == "two" and second.checked_at == NOW and second.created_at == now
    assert len(requests) == 1
    now += timedelta(minutes=10)
    # The mock now returns an expired result, which must never become a clean verdict.
    with pytest.raises(LinkSafetyError):
        service.lookup(URL, URL, "three")
    assert len(requests) == 2


def test_no_match_is_not_cached_for_new_checks():
    service, requests = provider()
    service.lookup(URL, URL, "one")
    service.lookup(URL, URL, "two")
    assert len(requests) == 2


@pytest.mark.parametrize("payload", [None, [], "", {"error": "oops"}, {"threat": None},
    {"threat": {}}, {"threat": {"threatTypes": [], "expireTime": MATCH["threat"]["expireTime"]}},
    {"threat": {"threatTypes": ["UNKNOWN"], "expireTime": MATCH["threat"]["expireTime"]}},
    {"threat": {"threatTypes": ["MALWARE"], "expireTime": "2026-09-15T00:10:00"}},
])
def test_malformed_success_payload_never_becomes_clean(payload):
    service = WebRiskClient("key", transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)), clock=lambda: NOW)
    with pytest.raises(LinkSafetyError) as failure:
        service.lookup(URL, URL, "one")
    assert failure.value.code == "LINK_SAFETY_INVALID_RESPONSE"


@pytest.mark.parametrize("status,code", [(403, "LINK_SAFETY_ACCESS_DENIED"), (401, "LINK_SAFETY_ACCESS_DENIED"),
    (429, "LINK_SAFETY_RATE_LIMITED"), (500, "LINK_SAFETY_UNAVAILABLE"), (302, "LINK_SAFETY_UNAVAILABLE")])
def test_provider_errors_are_sanitised(status, code):
    service, _ = provider({"error": "secret-key-private-provider-message"}, status)
    with pytest.raises(LinkSafetyError) as failure:
        service.lookup(URL, URL, "one")
    assert failure.value.code == code
    assert "secret" not in str(failure.value)


def test_timeout_and_missing_configuration():
    def timeout(request):
        raise httpx.ReadTimeout("secret URL", request=request)
    service = WebRiskClient("key", transport=httpx.MockTransport(timeout))
    with pytest.raises(LinkSafetyError, match="Unable to check"):
        service.lookup(URL, URL, "one")
    with pytest.raises(LinkSafetyError) as failure:
        WebRiskClient("").lookup(URL, URL, "one")
    assert failure.value.code == "LINK_SAFETY_NOT_CONFIGURED"


@pytest.fixture
def context(signed_analysis):
    service, requests = provider(MATCH)
    app.dependency_overrides[get_web_risk_client] = lambda: service
    with TestClient(app) as client:
        yield client, *signed_analysis, requests


def submit(client, key="link-first", url=URL):
    return client.post("/analysis/link-safety", json={"url": url}, headers={"Idempotency-Key": key})


def test_completed_link_history_replay_ownership_and_allowance(context):
    client, store, identity, requests = context
    first = submit(client)
    assert first.status_code == 200
    body = first.json()
    assert body["input_type"] == "link_safety"
    assert body["safety_status"] == "threat_detected" and "misinformation_risk_score" not in body
    assert submit(client).json() == body
    assert len(requests) == 1
    result_id = body["result_id"]
    assert store.documents["analysis_results", result_id]["user_id"] == "analysis-user"
    assert client.get(f"/analysis/results/{result_id}").json() == body
    assert client.get("/analysis/results").json()["results"] == [body]
    assert "user_id" not in body and "request_fingerprint" not in body
    assert store.documents["usage_allowances", "analysis-user"]["remaining_submissions"] == 0
    assert submit(client, "again").status_code == 429
    identity["user"] = AuthenticatedUser(uid="another", email="another@example.com", email_verified=True)
    store.documents["users", "another"] = {"uid": "another", "role": "free", "account_status": "active"}
    assert client.get(f"/analysis/results/{result_id}").status_code == 404
    assert client.get("/analysis/results").json()["results"] == []


def test_failure_saved_without_charge_and_retry_succeeds(context):
    client, store, _, _ = context
    broken, _ = provider(status=429)
    app.dependency_overrides[get_web_risk_client] = lambda: broken
    assert submit(client).status_code == 503
    history = client.get("/analysis/results").json()["results"]
    assert history[0]["input_type"] == "link_safety" and history[0]["processing_status"] == "failed"
    assert "safety_status" not in history[0]
    assert store.documents["usage_allowances", "analysis-user"]["remaining_submissions"] == 1
    assert ("analysis_locks", "analysis-user") not in store.documents
    assert submit(client).status_code == 409
    good, _ = provider()
    app.dependency_overrides[get_web_risk_client] = lambda: good
    retry = submit(client, "retry")
    assert retry.status_code == 200 and retry.json()["safety_status"] == "no_known_threats"


def test_invalid_link_does_not_reserve_or_call_provider(context):
    client, store, _, requests = context
    assert submit(client, url="http://localhost").status_code == 422
    assert not requests and ("usage_allowances", "analysis-user") not in store.documents


def test_unverified_suspended_and_unauthenticated_cannot_check(context):
    client, store, identity, requests = context
    identity["user"] = identity["user"].model_copy(update={"email_verified": False})
    assert submit(client).status_code == 403
    identity["user"] = identity["user"].model_copy(update={"email_verified": True})
    store.documents["users", "analysis-user"]["account_status"] = "suspended"
    assert submit(client).status_code == 403
    app.dependency_overrides.clear()
    assert submit(client).status_code == 401
    assert not requests


def test_same_key_cannot_cross_input_types_or_change_url(context):
    client, store, _, _ = context
    assert submit(client).status_code == 200
    assert submit(client, url="https://example.org/").status_code == 409
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as failure:
        store.reserve("analysis-user", "link-first", URL, input_type="text")
    assert failure.value.detail["error_code"] == "REQUEST_KEY_REUSED"
