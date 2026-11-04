"""Conservative comparison of citation URLs already validated by ``_public_url``."""

from hashlib import sha256
from typing import Literal
from urllib.parse import unquote_plus


def citation_comparison_key(url: str) -> str:
    """Ignore only OpenAI's exact tracking pair for citation identity checks.

    This key is never a replacement for the original display citation URL and
    does not validate, resolve, or request a URL. Keep every other URL component
    and raw query pair unchanged, including pair order and duplicate values.
    """
    before_fragment, fragment_marker, fragment = url.partition("#")
    base, query_marker, query = before_fragment.partition("?")
    if not query_marker:
        return url

    pairs = query.split("&")
    retained = []
    for pair in pairs:
        key, separator, value = pair.partition("=")
        if (separator and unquote_plus(key) == "utm_source"
                and unquote_plus(value) == "openai"):
            continue
        retained.append(pair)

    if len(retained) == len(pairs):
        return url
    query_suffix = "?" + "&".join(retained) if retained else ""
    return base + query_suffix + fragment_marker + fragment


def citation_match_kind(
    url: str, discovered: str,
) -> Literal["exact", "tracking_alias"] | None:
    """Classify one already validated citation/discovered URL pair."""
    if url == discovered:
        return "exact"
    if citation_comparison_key(url) == citation_comparison_key(discovered):
        return "tracking_alias"
    return None


def url_fingerprint(url: str) -> str:
    """Return an opaque, deterministic URL identifier for diagnostics."""
    return sha256(url.encode("utf-8")).hexdigest()
