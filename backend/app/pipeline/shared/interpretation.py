"""Conservative intent and relationship hints; never substitute a truth verdict."""

import re


def corporate_search_text(text):
    """Resolve a narrow company alias for discovery; keep the user's claim intact."""
    text = re.sub(r"\bSIA\b", "Singapore Airlines", text, flags=re.I)
    return re.sub(r"\bSingapore airline\b(?!\s+(?:industry|sector|companies|carriers)\b)",
                  "Singapore Airlines", text, flags=re.I)


def control_wording(text):
    return bool(re.search(r"\b(?:controlled\s+by|controlling\s+shareholder|voting\s+control)\b", text, re.I))


def ambiguous_control(text):
    return bool(re.search(r'\bis\s+controlled\s+by\b', text, re.I)
        and re.search(r'\b(?:SIA|Singapore Airlines?|Temasek|company|corporation|business|bank)\b', text, re.I)
        and not re.search(r'\b(?:not|never|if|unless|day.to.day|operational|operations|management|voting|ownership|owns|owned|shares?|shareholders?|shareholding|stake|funding)\b', text, re.I))


def input_intent(text):
    text = text.strip()
    # Explicit imagined scenarios are not assertions that the event will occur.
    # Mixed messages still go through claim extraction for their actual assertions.
    imagined = re.match(
        r"^(?:what\s+if|suppose(?:\s+that)?|imagine(?:\s+that)?|"
        r"what\s+would\s+happen\s+if|how\s+would\s+.+?\s+if)\b", text, re.I)
    conditional_question = re.match(r"^if\b.+?,\s*(?:how|what|where|who)\s+would\b", text, re.I)
    # A second conditional consequence question is still one imagined scenario.
    # Other extra sentences are left to extraction, so real assertions survive.
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Za-z])", text)
    pure_tail = all(re.match(r"^(?:how|what|where|who)\s+would\b", p, re.I) for p in parts[1:])
    if ((imagined or conditional_question) and pure_tail
            and not re.search(r"\b(?:but|actually|in reality|since|because)\b", text, re.I)):
        return "hypothetical"
    if text.endswith("?") or re.match(r"^(?:is|are|does|do|can|could|will|would|why|how|what)\b", text, re.I):
        return "question"
    return "assertion"


def claim_relationship(text):
    if ambiguous_control(text):
        return 'ambiguous_control'
    if re.search(r"\b(?:(?:run|ran|managed|operated)\s+by|runs|manages|operates|day.to.day|operational\s+control)\b", text, re.I):
        return "management"
    if control_wording(text) or re.search(r"\b(?:own(?:s|ed|ership)?|shareholders?|stakes?|shares?)\b", text, re.I):
        return "ownership"
    if re.search(r"\b(?:fund(?:s|ed|ing)?|financ(?:e|es|ed|ing)|bailout)\b", text, re.I):
        return "funding"
    return "general"


def relationship_queries(text):
    relation = claim_relationship(text)
    if relation == "general":
        return []
    focus = {
        'ambiguous_control': 'ownership voting control versus independent operational management',
        "management": "corporate governance board management operational decisions",
        "ownership": "annual report shareholders ownership voting rights",
        "funding": "annual report funding financing government investment",
    }[relation]
    # Normalise a known acronym in discovery only; preserve the quoted claim.
    topic = corporate_search_text(text)
    topic = re.sub(r"\b(?:is|are)\s+(?:run|ran|managed|operated|owned|funded|controlled)\s+by\b", "", topic, flags=re.I)
    topic = " ".join(topic.split())
    if relation == 'ambiguous_control':
        return [(topic[:240] + ' corporate governance independent business decisions')[:400],
                (topic[:240] + ' current ownership shareholders voting control')[:400]]
    if relation == 'ownership' and control_wording(text) and re.search(r'\bSingapore Airlines\b', topic, re.I):
        # Temasek is a discovery lead from the reviewed company registry, not an
        # assumed ownership link. The retrieved pages must establish the chain.
        return ['Singapore Airlines current controlling shareholders Temasek ownership voting rights',
                'Temasek Singapore government sole shareholder Singapore Airlines ownership official']
    return [(topic[:300] + " " + focus)[:400],
            (topic[:300] + " government role commercial decisions official statement")[:400]]


def relationship_page_priority(claim, title, url, snippet=""):
    relation = claim_relationship(claim)
    if relation == "general":
        return 0
    hints = {
        'ambiguous_control': r'governance|management|shareholding|ownership|history-of-temasek',
        "management": r"governance|management|board|government.role|independen",
        "ownership": r"shareholder|annual.report|ownership|investor",
        "funding": r"annual.report|financ|funding",
    }
    value = title + " " + url
    if relation == 'ambiguous_control':
        if url.rstrip('/').endswith('/en/about-us/history-of-temasek'):
            return 6
        if 'shareholding-info' in url:
            return 5
        if re.search(r'corporate.governance|independent|business decisions', value + ' ' + snippet, re.I):
            return 4
    if relation == 'ownership':
        if re.search(r'/about-us/information-for-investors/shareholding-info/?$', url, re.I):
            return 5
        if re.search(r'wholly.owned|deemed.interest|total.interest|ultimate.owner|sole.shareholder', value + ' ' + snippet, re.I):
            return 4
        if re.search(r'shareholding.info|sharehold(?:ers|ing)|majority.shareholder|sole.shareholder', value + ' ' + snippet, re.I):
            return 3
        if re.search(r'\b(?:19|20)\d{2}\b', title) or re.search(r'annualreport\d{4}\.pdf', url, re.I):
            return 1
    if relation == "management":
        if re.search(r"day.to.day|(?:not|never)\s+(?:direct|interfere)|business decisions", snippet, re.I):
            return 3
        if re.search(r"management.team|corporate.governance|commercial.decisions|interfer", value, re.I):
            return 2
        if re.search(r"sustainability", value, re.I):
            return 0
    return int(bool(re.search(hints[relation], value, re.I)))
