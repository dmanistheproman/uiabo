"""Discovery hints for passport entry rules, never evidence or verdicts."""

import re
from urllib.parse import unquote, urlsplit


def is_entry_validity_claim(claim: str) -> bool:
    if not re.search(r"\bpassports?\b", claim, re.I):
        return False
    if not re.search(r"\b(?:valid\w*|expir\w*)\b", claim, re.I):
        return False
    # An explicit outbound journey must not be silently changed into an entry
    # claim. Other ambiguous claims can explore an entry rule without assuming
    # it applies: the unchanged original still goes to semantic assessment.
    if re.search(r"\b(?:depart\w*|outbound|overseas|abroad|leaving)\b", claim, re.I):
        return False
    return bool(re.search(r"\b(?:ICA|enter\w*|entry|immigration|border|reject\w*|refus\w*)\b", claim, re.I))


def current_entry_query(claim: str) -> str | None:
    """A narrow authority lookup, without an alleged threshold/date or answer.

    ICA is resolved only as a discovery hint for Singapore. Explicit entry to
    another destination is left to the normal planner. Unknown authorities are
    also handled there; no destination or nationality is assigned to the user.
    """
    if not is_entry_validity_claim(claim):
        return None
    destination = re.search(r"\b(?:enter(?:ing)?|entry\s+(?:to|into)|arriv(?:al|ing)\s+in)\s+(?:the\s+)?(\w+)", claim, re.I)
    if destination and destination.group(1).casefold() != "singapore":
        return None
    if re.search(r"\bICA\b", claim, re.I) or re.search(r"\bSingapore\b", claim, re.I):
        return "Singapore ICA official current entry requirements passport validity exceptions"
    return None


def entry_page_priority(claim: str, title: str, url: str) -> int:
    """Rank relevant discovered page types before extraction, not their truth.

    Only title/path labels are used, so a navigation link or keyword in a large
    search snippet does not turn overseas travel advice into an entry page.
    URLs still go through the existing source policy and extraction validation.
    """
    if not is_entry_validity_claim(claim):
        return 0
    # Parent navigation paths can mention both entry and departure. Classify
    # the actual page label rather than that shared navigation vocabulary.
    leaf = unquote(urlsplit(url).path).rstrip("/").rsplit("/", 1)[-1]
    labels = title + " " + leaf.replace("-", " ").replace("_", " ")
    if re.search(r"\b(?:depart\w*|outbound|overseas|abroad|renew\w*|passport application)\b", labels, re.I):
        return -1
    if re.search(r"\b(?:entry requirements?|entering|immigration requirements?|admission requirements?)\b", labels, re.I):
        return 1
    return 0
