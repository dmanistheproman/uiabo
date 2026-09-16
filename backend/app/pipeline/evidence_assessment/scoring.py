"""Versioned, continuous evidence scoring. Constants are prototype policy choices."""

import re
from urllib.parse import urlsplit

from app.pipeline.shared.models import ScoringSummary

MIN_DECISIVE_QUALITY = 0.60
SCORING_VERSION = "evidence-v3"
LABELS = {
    "supported": "Low Concern", "contradicted": "High Concern",
    "conflicting": "Needs Caution", "insufficient_evidence": "Not Enough Information",
}


def group_evidence(assessed, sources):
    """One strongest vote per origin/stance; exact copied passages share an origin.

    Missing provenance uses hostname, never evidence ID. Distinct hostnames alone
    do not earn a corroboration bonus. Different stances are always retained.
    """
    parents = {}

    def find(key):
        parents.setdefault(key, key)
        if parents[key] != key:
            parents[key] = find(parents[key])
        return parents[key]

    def merge(a, b):
        parents[find(a)] = find(b)

    origin_keys = {}
    for item in assessed:
        source = sources[item.evidence_id]
        host = (urlsplit(str(source.url)).hostname or "unknown").removeprefix("www.")
        origin = source.provenance.origin_group if source.provenance else host
        key = "origin:" + origin.casefold()
        origin_keys[item.evidence_id] = key
        merge(key, "host:" + host)
        merge(key, "publisher:" + source.publisher.strip().casefold())
        merge(key, "passage:" + re.sub(r"\s+", " ", source.passage).strip().casefold())
    def rank(vote):
        return (vote.quality_score, bool(sources[vote.evidence_id].provenance), vote.evidence_id)

    groups = {}
    for item in assessed:
        key = (find(origin_keys[item.evidence_id]), item.stance)
        if key not in groups or rank(item) > rank(groups[key]):
            groups[key] = item
    return list(groups.values())


def _strength(items, sources):
    if not items:
        return 0.0
    ordered = sorted(items, key=lambda item: (
        item.quality_score, bool(sources[item.evidence_id].provenance), item.evidence_id
    ), reverse=True)
    strongest = ordered[0].quality_score
    # A bounded bonus requires explicit source-origin metadata on both sides.
    corroboration = 0.0
    if sources[ordered[0].evidence_id].provenance:
        corroboration = min(0.06, 0.04 * sum(
            item.quality_score for item in ordered[1:]
            if sources[item.evidence_id].provenance
        ))
    return round(min(1.0, strongest + corroboration), 4)


def score_evidence(voting, sources):
    support = [item for item in voting if item.stance == "supporting"]
    contradict = [item for item in voting if item.stance == "contradicting"]
    s, c = _strength(support, sources), _strength(contradict, sources)
    outcome = ("conflicting" if support and contradict else "supported" if support
               else "contradicted" if contradict else "insufficient_evidence")
    # Decide the verdict from admissible stances BEFORE computing the indicator.
    score = round(round(50 * (1 - s + c), 8))
    provisional = not (support or contradict)
    strength = max(s, c)
    level = ("Insufficient" if provisional else "Strong" if strength >= 0.90
             else "Moderate" if strength >= 0.75 else "Limited")
    reasons = []
    if provisional:
        reasons.append("No sufficiently strong evidence establishes or contradicts the complete claim.")
        reasons.append("50 is a provisional neutral starting point, not a 50% chance of being false. Missing evidence is not proof of truth or falsity.")
    else:
        reasons.append(f"{len(support)} supporting and {len(contradict)} contradicting source groups meet relevance, scope and quality checks.")
        reasons.append("Repeated publishers, hosts and identical passages do not add votes. Corroboration bonuses require recorded source origins.")
    if outcome == "conflicting":
        reasons.append("Evidence strength describes the sources, not agreement: applicable evidence exists on both sides.")
    reasons.append("This is a rule-based evidence indicator, not a probability that the claim is false. A score of 0 means no concern identified in the evidence checked.")
    return outcome, score, ScoringSummary(
        version=SCORING_VERSION, status="provisional" if provisional else "evidence_based",
        evidence_strength=level, supporting_strength=s, contradicting_strength=c,
        supporting_origins=len(support), contradicting_origins=len(contradict), reasons=reasons,
    )


def unscored_summary(reason):
    return ScoringSummary(version=SCORING_VERSION, status="not_applicable",
                          evidence_strength="Insufficient", reasons=[reason])


def provisional_summary(reason):
    return ScoringSummary(version=SCORING_VERSION, status="provisional",
        evidence_strength="Insufficient", reasons=[reason,
            "50 is a provisional neutral starting point, not a 50% chance of being false. Missing evidence is not proof of truth or falsity."])
