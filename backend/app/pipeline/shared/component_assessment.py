"""Persisted evidence findings for material parts of causal claims."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .components import ClaimComponent, decompose_claim


class ComponentQuote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: str
    quote: str = Field(min_length=1, max_length=12000)


class ComponentFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    component_id: str
    stance: Literal["supporting", "contradicting", "unresolved"]
    basis: Literal["direct", "inference", "none"]
    evidence_ids: list[str] = Field(default_factory=list, max_length=8)
    quotes: list[ComponentQuote] = Field(default_factory=list, max_length=8)
    explanation: str = Field(min_length=1, max_length=4000)
    scope_matched: bool
    quality_score: float = Field(default=0, ge=0, le=1)

    @model_validator(mode="after")
    def grounded_vote(self):
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("Duplicate component evidence IDs")
        if set(self.evidence_ids) != {q.evidence_id for q in self.quotes}:
            raise ValueError("Every component source must have a quotation")
        if self.stance != "unresolved":
            if not self.scope_matched or self.basis == "none" or not self.quotes or self.quality_score < .6:
                raise ValueError("A component vote requires applicable, quoted, adequate evidence")
            if self.basis == "inference" and self.quality_score > .7:
                raise ValueError("Indirect component findings have a bounded strength")
        elif self.basis != "none" or self.quality_score or self.scope_matched:
            raise ValueError("An unresolved component cannot carry a decisive vote")
        return self


class ComponentAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal["components-v1"] = "components-v1"
    finding: Literal["material_contradiction", "material_support", "conflicting", "unresolved"]
    components: list[ClaimComponent] = Field(min_length=3, max_length=3)
    findings: list[ComponentFinding] = Field(min_length=3, max_length=24)
    explanation: str = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def validate_finding(self):
        ids = [c.component_id for c in self.components]
        if len(ids) != len(set(ids)) or set(ids) != {f.component_id for f in self.findings}:
            raise ValueError("Each component must have findings, with no unknown components")
        if self.finding != aggregate_finding(self.components, self.findings):
            raise ValueError("Overall component finding must follow its material evidence")
        return self


def component_stances(components, findings):
    return {c.component_id: {f.stance for f in findings if f.component_id == c.component_id
            and f.stance != "unresolved"} for c in components if c.material}


def aggregate_finding(components, findings):
    stances = component_stances(components, findings)
    if any(s == {"contradicting"} for s in stances.values()):
        return "material_contradiction"
    if any(s == {"supporting", "contradicting"} for s in stances.values()):
        return "conflicting"
    if stances and all(s == {"supporting"} for s in stances.values()):
        return "material_support"
    return "unresolved"


def component_votes(components, findings, sources):
    """Select scoring votes once, shared by live aggregation and saved validation."""
    from .models import AssessedEvidence
    from ..evidence_assessment.scoring import group_evidence, score_evidence
    finding = aggregate_finding(components, findings)
    stances = component_stances(components, findings)
    if finding == "material_contradiction":
        selected = {key for key, values in stances.items() if values == {"contradicting"}}
        eligible = [f for f in findings if f.component_id in selected and f.stance == "contradicting"]
    elif finding == "conflicting":
        selected = {key for key, values in stances.items() if len(values) == 2}
        eligible = [f for f in findings if f.component_id in selected and f.stance != "unresolved"]
    elif finding == "material_support":
        def strength(key):
            votes = [AssessedEvidence(evidence_id=eid, stance="supporting", quality_score=f.quality_score,
                assessment_reason=f.explanation) for f in findings if f.component_id == key and f.stance == "supporting"
                for eid in f.evidence_ids]
            return score_evidence(group_evidence(votes, sources), sources)[2].supporting_strength
        selected_id = min(stances, key=strength)
        eligible = [f for f in findings if f.component_id == selected_id and f.stance == "supporting"]
    else:
        eligible = []
    return [AssessedEvidence(evidence_id=eid, stance=f.stance, quality_score=f.quality_score,
        assessment_reason=f.explanation, evidence_quote=next(q.quote for q in f.quotes if q.evidence_id == eid))
        for f in eligible for eid in f.evidence_ids]


def validate_component_result(result, text=None, sources=None):
    assessment = result.component_assessment
    if assessment is None:
        return
    if text is not None and assessment.components != decompose_claim(text):
        raise ValueError("Component text and scope must be grounded in the original assertion")
    expected = {"material_contradiction": "contradicted", "material_support": "supported",
                "conflicting": "conflicting", "unresolved": "insufficient_evidence"}[assessment.finding]
    if result.assessment_outcome != expected:
        raise ValueError("Component and final outcomes disagree")
    available = sources if sources is not None else {e.evidence_id: e for e in result.assessed_evidence}
    for finding in assessment.findings:
        for quote in finding.quotes:
            if quote.evidence_id not in available:
                raise ValueError("Component finding refers to an unknown source")
            if sources is not None and quote.quote not in available[quote.evidence_id].passage:
                raise ValueError("Component quote must occur in its returned source passage")
    if sources is not None:
        from ..evidence_assessment.scoring import group_evidence, score_evidence
        votes = component_votes(assessment.components, assessment.findings, sources)
        outcome, score, summary = score_evidence(group_evidence(votes, sources), sources)
        fields = ("status", "evidence_strength", "supporting_strength", "contradicting_strength",
                  "supporting_origins", "contradicting_origins")
        if (result.assessment_outcome != outcome or result.misinformation_risk_score != score
                or not result.scoring or any(getattr(result.scoring, key) != getattr(summary, key) for key in fields)):
            raise ValueError("Component score must match the admitted component evidence")
