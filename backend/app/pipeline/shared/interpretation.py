"""Conservative intent and relationship hints; never substitute a truth verdict."""

import re


def input_intent(text):
    text = text.strip()
    # Explicit imagined scenarios are not assertions that the event will occur.
    # Mixed messages still go through claim extraction for their actual assertions.
    if (re.match(r"^(?:what\s+if|suppose(?:\s+that)?|imagine(?:\s+that)?)\b", text, re.I)
            and not re.search(r"[.!?]\s+\w|\b(?:but|actually|in reality)\b", text, re.I)):
        return "hypothetical"
    if text.endswith("?") or re.match(r"^(?:is|are|does|do|can|could|will|would|why|how|what)\b", text, re.I):
        return "question"
    return "assertion"


def claim_relationship(text):
    if re.search(r"\b(?:(?:run|ran|managed|operated|controlled)\s+by|runs|manages|operates|day.to.day|operational\s+control)\b", text, re.I):
        return "management"
    if re.search(r"\b(?:own(?:s|ed|ership)?|shareholders?|stakes?|shares?)\b", text, re.I):
        return "ownership"
    if re.search(r"\b(?:fund(?:s|ed|ing)?|financ(?:e|es|ed|ing)|bailout)\b", text, re.I):
        return "funding"
    return "general"


def relationship_queries(text):
    relation = claim_relationship(text)
    if relation == "general":
        return []
    focus = {
        "management": "corporate governance board management operational decisions",
        "ownership": "annual report shareholders ownership voting rights",
        "funding": "annual report funding financing government investment",
    }[relation]
    # Normalise a known acronym in discovery only; preserve the quoted claim.
    topic = re.sub(r"\bSIA\b", "Singapore Airlines", text)
    topic = re.sub(r"\b(?:is|are)\s+(?:run|ran|managed|operated|owned|funded)\s+by\b", "", topic, flags=re.I)
    topic = " ".join(topic.split())
    return [(topic[:300] + " " + focus)[:400],
            (topic[:300] + " government role commercial decisions official statement")[:400]]


def relationship_page_priority(claim, title, url, snippet=""):
    relation = claim_relationship(claim)
    if relation == "general":
        return 0
    hints = {
        "management": r"governance|management|board|government.role|independen",
        "ownership": r"shareholder|annual.report|ownership|investor",
        "funding": r"annual.report|financ|funding",
    }
    value = title + " " + url
    if relation == "management":
        if re.search(r"day.to.day|(?:not|never)\s+(?:direct|interfere)|business decisions", snippet, re.I):
            return 3
        if re.search(r"management.team|corporate.governance|commercial.decisions|interfer", value, re.I):
            return 2
        if re.search(r"sustainability", value, re.I):
            return 0
    return int(bool(re.search(hints[relation], value, re.I)))
