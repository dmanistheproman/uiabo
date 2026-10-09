"""Conservative causal-claim decomposition, never evidence or a verdict.

Every component is an exact span of the original claim. Ambiguous scope stays
with the existing whole-claim assessment rather than becoming invented facts.
"""

import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field


class ClaimComponent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    component_id: str = Field(min_length=1, max_length=40)
    text: str = Field(min_length=1, max_length=5000)
    kind: Literal["event", "premise", "causal_link"]
    material: bool = True
    time_scope: Literal["current", "stated", "unspecified"]


_CAUSAL = re.compile(r"\b(?:because(?:\s+of)?|due\s+to|owing\s+to|as\s+a\s+result\s+of)\b", re.I)
_UNSAFE_SCOPE = re.compile(
    r"\b(?:if|unless|suppose|supposing|hypothetical(?:ly)?|imagine|might|may|could|would|"
    r"perhaps|possibly|allegedly|reportedly|not|never|no|den(?:y|ies|ied)|"
    r"say|says|said|claim|claims|claimed|rumou?r|according\s+to)\b|n['’]t\b", re.I)
_DISCUSSION = re.compile(r"\b(?:is|are)\s+(?:currently\s+)?(?:discussing|considering|debating|planning|proposing)\b", re.I)
_STATED_TIME = re.compile(r"\b(?:19\d{2}|20\d{2}|yesterday|tomorrow|last|next|ago|"
                          r"january|february|march|april|may|june|july|august|september|october|november|december)\b", re.I)
_PRESENT = re.compile(r"\b(?:is|are|am|has|have|does|do)\b", re.I)
_COUNTRIES = re.compile(
    r"\b(?:Singapore|United Kingdom|United States|Britain|Malaysia|Australia|"
    r"New Zealand|Canada|India|Thailand|France|Brazil|Indonesia|Philippines)\b", re.I)


def cpf_retirement_context(text: str) -> bool:
    """Scoped acronym expansion for discovery only, never a source verdict."""
    if re.search(r"\bCentral Provident Fund\b", text, re.I):
        return True
    if not (re.search(r"\bCPF\b", text, re.I)
            and re.search(r"\b(?:retirement|retire|pension|savings|MediSave|MediShield|CPF LIFE)\b", text, re.I)):
        return False
    if re.search(r"\b(?:Charoen|Pokphand|Foods?|Central Pacific|NYSE|ticker|stock|shares|shareholders?|corporate)\b", text, re.I):
        return False
    # Another explicit jurisdiction must not be silently replaced with Singapore.
    return not any(m.group().casefold() != "singapore" for m in _COUNTRIES.finditer(text))


def component_discovery_anchor(text: str) -> str:
    if cpf_retirement_context(text):
        return "Singapore Central Provident Fund (CPF)"
    countries = list(dict.fromkeys(m.group() for m in _COUNTRIES.finditer(text)))
    return " ".join(countries) if len(countries) == 1 else ""


def component_page_priority(claim: str, title: str, url: str, snippet: str = "", *, as_of=None) -> int:
    """Keep subject-matching pages ahead of acronym lookalikes, not as evidence."""
    if not decompose_claim(claim) or not cpf_retirement_context(claim):
        return 0
    host = (urlsplit(url).hostname or "").lower()
    value = title + " " + url.replace("-", " ") + " " + snippet
    primary = any(host == domain or host.endswith("." + domain)
                  for domain in ("cpf.gov.sg", "mof.gov.sg", "mom.gov.sg"))
    named = bool(re.search(r"\bCentral Provident Fund\b|\bSingapore\b", value, re.I))
    if not primary and not named:
        return 0
    score = 3 if primary else 1
    if re.search(r"\b(?:reserves?|fund(?:ing|ed)?|financial|accounts?|assets?|liabilities|annual.report|retirement.age)\b", value, re.I):
        score += 2
    if as_of:
        years = [int(year) for year in re.findall(r"(?<!\d)(20\d{2})(?!\d)", title + " " + url)]
        # For a present allegation, avoid spending all slots on old accounts.
        # Publication age only orders discovery; it never determines applicability.
        if years and max(years) < as_of.year - 2 and not _STATED_TIME.search(claim):
            score -= 2
    return score

COMPONENT_GUIDANCE = """CAUSAL CLAIM COMPONENTS: When claim_components are supplied,
they are exact parts of the user's assertion, not established facts. Investigate
the event, its material factual premise and their claimed causal connection
separately. A source may address only the premise and still be useful. Lack of
support for a premise is not a contradiction. An ordinary current policy does
not disprove unannounced discussions or a future change. 'Are discussing' alleges
present discussion as of the assessment date unless the claim states another
period; a missing implementation date is not missing timing for the discussion.
This interpretation does not establish that any discussion occurred. Preserve
all scope and qualifications, and do not invent missing financial periods,
comparators, populations or causes. A general funding mechanism alone does not
necessarily settle a claim that balances are falling faster than expected.
"""


def _time_scope(text):
    if _STATED_TIME.search(text):
        return "stated"
    if _DISCUSSION.search(text):
        return "current"
    return "current" if _PRESENT.search(text) else "unspecified"


def decompose_claim(text: str) -> list[ClaimComponent]:
    """Split only one unambiguous asserted cause; leave complex scope intact."""
    if not isinstance(text, str) or not 1 <= len(text) <= 5000:
        return []
    claim = text.strip()
    if (_UNSAFE_SCOPE.search(claim) or re.search(r'[?"“”]|(?:^|\s)[\'‘]|[\'’](?:\s|$)', claim)
            or re.search(r"[.!]\s+\S|[;\n\r]", claim)):
        return []
    matches = list(_CAUSAL.finditer(claim))
    if len(matches) != 1:
        return []
    match = matches[0]
    event = claim[:match.start()].strip().rstrip(",").rstrip()
    premise = claim[match.end():].strip()
    if len(event.split()) < 3 or len(premise.split()) < 3:
        return []
    # Avoid detached pronouns that require rewriting the cause into a different
    # assertion. Ordinary possessives inside an otherwise explicit span remain.
    if re.match(r"(?:this|that|it|they|these|those|which)\b", premise, re.I):
        return []
    return [
        ClaimComponent(component_id="event", text=event, kind="event", time_scope=_time_scope(event)),
        ClaimComponent(component_id="premise", text=premise, kind="premise", time_scope=_time_scope(premise)),
        ClaimComponent(component_id="causal_link", text=claim, kind="causal_link", time_scope=_time_scope(event)),
    ]


def component_queries(text: str) -> list[str]:
    """Neutral discovery for each material part; original claim is unchanged."""
    components = decompose_claim(text)
    if not components:
        return []
    anchor = component_discovery_anchor(text)
    queries = []
    for component in components[:2]:
        topic = " ".join(component.text.split())
        # Never truncate a qualification or pass user-supplied search operators.
        if len(topic) > 350 or re.search(r"https?://|\bsite:", topic, re.I):
            return []
        suffix = " official evidence sources"
        if component.kind == "premise" and re.search(r"\b(?:reserves?|funds?|funding|assets?|liabilities|financ\w*|deficit|surplus|debt)\b", topic, re.I):
            suffix = " official financial statements assets liabilities"
        # A component may omit the entity/jurisdiction named elsewhere in the
        # original sentence. Carry that discovery context into both queries.
        # CPF's expansion is scoped above to retirement/savings, excluding its
        # stock-ticker and corporate-food uses. No original span is rewritten.
        topic = " ".join(filter(None, [anchor, topic]))
        if len(topic) + len(suffix) > 400:
            return []
        queries.append(topic + suffix)
    return queries
