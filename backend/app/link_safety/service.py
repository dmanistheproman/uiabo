"""Web Risk Lookup client. Never fetches or follows the submitted URL."""

from collections import OrderedDict
from datetime import datetime, timezone
from functools import lru_cache
from hashlib import sha256
from ipaddress import ip_address
import os
from pathlib import Path
import re
from threading import RLock

from dotenv import load_dotenv
import httpx
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from app.link_safety.models import LinkSafetyResult, ThreatType


ENDPOINT = "https://webrisk.googleapis.com/v1/uris:search"
THREAT_TYPES = ("MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE")


class LinkSafetyError(Exception):
    def __init__(self, code, message, status=503):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def validate_url(value: str) -> str:
    """Accept public HTTP(S) URLs without visiting them or resolving their DNS."""
    value = value.strip()
    try:
        if not value or re.search(r"[\s\\\x00-\x1f\x7f]", value):
            raise ValueError()
        parsed = TypeAdapter(AnyHttpUrl).validate_python(value)
        if parsed.username is not None or parsed.password is not None:
            raise ValueError()
        host = (parsed.host or "").strip("[]").rstrip(".").lower()
        try:
            address = ip_address(host)
        except ValueError:
            if "." not in host or host.endswith((".localhost", ".local", ".internal", ".lan", ".home", ".test", ".invalid")):
                raise ValueError()
        else:
            if not address.is_global:
                raise ValueError()
        return str(parsed)
    except (ValueError, ValidationError):
        raise LinkSafetyError("INVALID_LINK", "Enter a full public webpage URL starting with https:// or http://, without login credentials.", 422) from None


class _Threat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    threatTypes: list[ThreatType] = Field(min_length=1)
    expireTime: datetime


class _LookupResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    threat: _Threat


class WebRiskClient:
    def __init__(self, api_key, *, transport=None, clock=None, cache_size=2048):
        self.api_key = api_key
        self.transport = transport
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.cache_size = cache_size
        self.cache = OrderedDict()
        self.lock = RLock()

    def lookup(self, submitted_url, checked_url, result_id):
        if not self.api_key:
            raise LinkSafetyError("LINK_SAFETY_NOT_CONFIGURED", "Link safety checks are not available yet. Please try again later.")
        now = self.clock()
        cache_key = sha256(checked_url.encode()).hexdigest()
        with self.lock:
            entry = self.cache.get(cache_key)
            if entry and entry[1] > now:
                types, expires_at, checked_at = entry
                self.cache.move_to_end(cache_key)
                return self._result(submitted_url, checked_url, result_id, types, expires_at, checked_at, True)
            self.cache.pop(cache_key, None)

        params = [("uri", checked_url)] + [("threatTypes", item) for item in THREAT_TYPES]
        # A header keeps the credential out of URLs and ordinary access logs.
        try:
            with httpx.Client(timeout=httpx.Timeout(15.0, connect=5.0), follow_redirects=False,
                              transport=self.transport) as client:
                response = client.get(ENDPOINT, params=params, headers={"X-Goog-Api-Key": self.api_key})
        except httpx.RequestError:
            raise LinkSafetyError("LINK_SAFETY_UNAVAILABLE", "Unable to check this link right now. Please try again.") from None
        if response.status_code in (401, 403):
            raise LinkSafetyError("LINK_SAFETY_ACCESS_DENIED", "The link safety service is not available for this app yet. Please try again later.")
        if response.status_code == 429:
            raise LinkSafetyError("LINK_SAFETY_RATE_LIMITED", "The link safety service is busy. Please try again later.")
        if response.status_code != 200:
            raise LinkSafetyError("LINK_SAFETY_UNAVAILABLE", "Unable to check this link right now. Please try again.")
        checked_at = self.clock()
        try:
            payload = response.json()
            if payload == {}:
                types, expires_at = [], None
            else:
                threat = _LookupResponse.model_validate(payload).threat
                types = sorted(set(threat.threatTypes))
                expires_at = threat.expireTime
                if expires_at.tzinfo is None or expires_at <= checked_at:
                    raise ValueError("Invalid threat expiration")
        except (ValueError, ValidationError):
            raise LinkSafetyError("LINK_SAFETY_INVALID_RESPONSE", "The link safety service returned an incomplete result. Please try again.") from None
        # Google requires positive matches to be cached until expireTime.
        # Empty responses have no expiry and are not reused for new checks.
        if types:
            with self.lock:
                self.cache[cache_key] = (types, expires_at, checked_at)
                self.cache.move_to_end(cache_key)
                while len(self.cache) > self.cache_size:
                    self.cache.popitem(last=False)
        return self._result(submitted_url, checked_url, result_id, types, expires_at, checked_at, False)

    def _result(self, submitted_url, checked_url, result_id, types, expires_at, checked_at, cached):
        return LinkSafetyResult(
            result_id=result_id, submitted_url=submitted_url, checked_url=checked_url,
            safety_status="threat_detected" if types else "no_known_threats",
            threat_types=types, checked_at=checked_at, threat_expires_at=expires_at, cached=cached,
            explanation=("Google Web Risk flagged this URL as potentially dangerous."
                         if types else "Google Web Risk did not find this URL on the threat lists checked."),
            recommended_action=("Avoid opening this link, downloading files or entering personal information. Contact the organisation through a website or phone number you already trust."
                                if types else "Stay cautious. Verify the sender and website address before entering passwords, making payments or downloading files."),
            created_at=self.clock(),
        )


@lru_cache
def get_web_risk_client():
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    return WebRiskClient(os.getenv("WEB_RISK_API_KEY", "").strip())
