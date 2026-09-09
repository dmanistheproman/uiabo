"""Discovery URL validation and conservative, documented source eligibility.

Eligibility permits assessment; it does not establish expertise, independence,
page authorship or truth. Unknown publishers remain leads. No model trust score.
All network extraction goes through Tavily, never arbitrary backend URL fetches.
"""

from dataclasses import dataclass
import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit

from .sources import SOURCES, canonical_url, source_details, SourceNotAllowed

# Registry policies are linked in evaluation/trusted_sources/README.md.
GOVERNMENT_NAMESPACES = ("gov.uk", "gov.au", "gov")
BLOCKED_HOSTS = ("localhost", "local", "internal", "test", "invalid", "example")
LEAD_ONLY_PLATFORMS = ("facebook.com", "instagram.com", "reddit.com", "tiktok.com", "youtube.com", "quora.com")


def public_url(value: str) -> str:
    """Syntactic public-web boundary, not a DNS/redirect security guarantee."""
    if (not isinstance(value, str) or len(value) > 2048
            or re.search(r"[\s\\\x00-\x1f\x7f]", value)):
        raise ValueError("Invalid public URL")
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower().rstrip(".")
    if (parsed.scheme not in {"https", "http"} or parsed.username is not None
            or parsed.password is not None or parsed.port not in {None, 443 if parsed.scheme == "https" else 80}
            or "." not in host or not re.fullmatch(r"[a-z0-9.-]+", host)
            or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in host.split("."))
            or any(host == suffix or host.endswith("." + suffix) for suffix in BLOCKED_HOSTS)):
        raise ValueError("Invalid public URL")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if re.fullmatch(r"[0-9.]+", host):
            raise ValueError("IP-style URL is not accepted") from None
    else:
        raise ValueError("IP URLs are not accepted")
    if host.startswith("www."):
        host = host[4:]
    # Only legacy-approved URLs lose tracking; unknown query semantics survive.
    clean = urlunsplit((parsed.scheme, host, parsed.path or "/", parsed.query, ""))
    try:
        return canonical_url(clean)
    except SourceNotAllowed:
        return clean


@dataclass(frozen=True)
class SourceDecision:
    eligible: bool
    policy: str
    publisher: str
    source_type: str
    origin_group: str
    reason: str


def classify_source(url: str) -> SourceDecision:
    host = urlsplit(public_url(url)).hostname
    for domain in SOURCES:
        if host == domain or host.endswith("." + domain):
            publisher, kind = source_details(url)
            origin = ("thailand-government" if domain in {"mfa.go.th", "thaiembassy.org"}
                      else "gov" if kind == "government" and domain.endswith(".gov") else domain)
            return SourceDecision(True, "catalogue", publisher, kind, origin,
                "Publisher is in the reviewed prototype catalogue; passage relevance and applicability are checked separately.")
    for suffix in GOVERNMENT_NAMESPACES:
        if host == suffix or host.endswith("." + suffix):
            # Conservatively group national government families; do not claim
            # that different departments are independent corroboration.
            return SourceDecision(True, "government_namespace", host, "government", suffix,
                f"Hostname is within the registration-restricted .{suffix} namespace. This does not certify page content or topical authority.")
    return SourceDecision(False, "unverified", host, "other", host,
        "Publisher identity is outside the reviewed catalogue and recognised government namespaces; used only as a search lead.")


def extractable_lead(url):
    host = urlsplit(public_url(url)).hostname
    return not any(host == domain or host.endswith("." + domain) for domain in LEAD_ONLY_PLATFORMS)


def original_links(markdown: str) -> list[str]:
    """Follow only literal, eligible source links; never an LLM-invented URL."""
    found = []
    for value in re.findall(r"https?://[^\s<>\]\)\"']+", markdown[:60000]):
        try:
            clean = public_url(value.rstrip(".,;"))
            if classify_source(clean).eligible and clean not in found:
                found.append(clean)
        except ValueError:
            continue
    return found[:8]
