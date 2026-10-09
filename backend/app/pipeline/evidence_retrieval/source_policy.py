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
from app.pipeline.shared.interpretation import claim_relationship
from app.pipeline.shared.rankings import political_salary_ranking

# Registry policies are linked in evaluation/trusted_sources/README.md.
GOVERNMENT_NAMESPACES = ("gov.uk", "gov.au", "gov")
BLOCKED_HOSTS = ("localhost", "local", "internal", "test", "invalid", "example")
LEAD_ONLY_PLATFORMS = ("facebook.com", "instagram.com", "reddit.com", "tiktok.com", "youtube.com", "quora.com")

# Reviewed identities, narrowly scoped to corporate relationships. This registry
# grants eligibility, never truth. See CLAIM_INTERPRETATION.md for review links.
FIRST_PARTY = {
    "temasek.com.sg": ("Temasek", r"\b(?:Temasek|SIA|Singapore Airlines)\b", "temasek-portfolio"),
    "singaporeair.com": ("Singapore Airlines", r"\b(?:SIA|Singapore Airlines)\b", "temasek-portfolio"),
}


def preferred_corporate_domains(claim):
    domains = [domain for domain in FIRST_PARTY if classify_source("https://" + domain, claim).eligible]
    return ["gov.sg", *domains] if domains else None


def public_url(value: str) -> str:
    """Validate a fetch URL without changing its hostname, path or query semantics.

    Syntactic public-web boundary, not a DNS/redirect security guarantee.
    """
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
    return urlunsplit((parsed.scheme, host, parsed.path or "/", parsed.query, ""))


def url_identity(value: str) -> str:
    """Deduplication key only: never send this normalised URL to extraction."""
    clean = public_url(value)
    try:
        return canonical_url(clean)
    except SourceNotAllowed:
        parsed = urlsplit(clean)
        host = parsed.hostname.removeprefix("www.")
        return urlunsplit((parsed.scheme, host, parsed.path, parsed.query, ""))


@dataclass(frozen=True)
class SourceDecision:
    eligible: bool
    policy: str
    publisher: str
    source_type: str
    origin_group: str
    reason: str


def classify_source(url: str, claim: str = "") -> SourceDecision:
    host = urlsplit(public_url(url)).hostname
    if (host in {"politicalsalaries.com", "www.politicalsalaries.com"}
            and political_salary_ranking(claim)):
        return SourceDecision(True, "catalogue", "Political Salaries", "other", "politicalsalaries.com",
            "Reviewed political-pay comparison project for salary-ranking claims only. Manually compiled public figures can be incomplete or dated; verify metric, period and underlying sources.")
    for domain, (publisher, subjects, origin) in FIRST_PARTY.items():
        if ((host == domain or host.endswith("." + domain))
                and claim_relationship(claim) != "general" and re.search(subjects, claim, re.I)):
            return SourceDecision(True, "scoped_first_party", publisher, "other", origin,
                "Reviewed first-party publisher for its own corporate relationships. Check that the passage establishes the named company's scope; self-publication is not independent corroboration.")
    for domain in SOURCES:
        if host == domain or host.endswith("." + domain):
            publisher, kind = source_details(url)
            origin = ("bbc" if domain in {"bbc.com", "bbc.co.uk"} else
                      "thailand-government" if domain in {"mfa.go.th", "thaiembassy.org"}
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


def original_links(markdown: str, claim: str = "") -> list[str]:
    """Follow only literal, eligible source links; never an LLM-invented URL."""
    found = []
    for value in re.findall(r"https?://[^\s<>\]\)\"']+", markdown[:60000]):
        try:
            clean = public_url(value.rstrip(".,;"))
            if classify_source(clean, claim).eligible and clean not in found:
                found.append(clean)
        except ValueError:
            continue
    return found[:8]
