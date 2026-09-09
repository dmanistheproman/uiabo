"""Initial source scope for the English Sprint 1 prototype.

Domain inclusion controls where we search; it does not establish factual truth.
Maintenance notes: evaluation/trusted_sources/README.md.
"""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


SOURCES = {
    "gov.sg": ("Singapore Government", "government"),
    "mfa.go.th": ("Thailand Ministry of Foreign Affairs", "government"),
    "thaiembassy.org": ("Royal Thai Embassy", "government"),
    "nasa.gov": ("NASA", "government"),
    "snopes.com": ("Snopes", "fact_check"),
    "fullfact.org": ("Full Fact", "fact_check"),
    "factcheck.org": ("FactCheck.org", "fact_check"),
    "reuters.com": ("Reuters", "news"),
    "apnews.com": ("Associated Press", "news"),
    "channelnewsasia.com": ("CNA", "news"),
    "nus.edu.sg": ("National University of Singapore", "academic"),
}


class SourceNotAllowed(ValueError):
    """A valid-looking URL is outside the deliberately limited source scope."""


def canonical_url(value: str) -> str:
    """Reject unsupported URLs; remove tracking without dropping article IDs."""
    if not isinstance(value, str) or any(c.isspace() for c in value):
        raise ValueError("Invalid citation URL")
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower().rstrip(".")
    if (parsed.scheme not in {"http", "https"} or not host
            or parsed.username is not None or parsed.password is not None
            or parsed.port not in {None, 443 if parsed.scheme == "https" else 80}):
        raise ValueError("Invalid citation URL")
    if host.startswith("www."):
        host = host[4:]
    if not any(host == domain or host.endswith("." + domain) for domain in SOURCES):
        raise SourceNotAllowed("Source outside prototype catalogue")
    query = [(key, val) for key, val in parse_qsl(parsed.query, keep_blank_values=True)
             if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}]
    return urlunsplit((parsed.scheme, host, parsed.path.rstrip("/") or "/", urlencode(sorted(query)), ""))


def source_details(url: str) -> tuple[str, str]:
    host = urlsplit(canonical_url(url)).hostname
    for domain, (publisher, source_type) in SOURCES.items():
        if host == domain or host.endswith("." + domain):
            # Keep the precise agency hostname for the broad government family.
            return (host if domain == "gov.sg" else publisher, source_type)
    raise ValueError("Unknown source")
