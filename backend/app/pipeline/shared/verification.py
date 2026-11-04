"""Bounded, provenance-preserving contracts for general claim verification.

These describe what needs checking and what the retrieved passages establish.
They do not turn missing evidence into a contradiction or a probability.
"""

from datetime import date
import re
from typing import Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator


class VerificationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class VerificationAssertion(VerificationModel):
    id: str = Field(pattern=r"^a[1-5]$")
    text: str = Field(min_length=1, max_length=5000)
    material: Literal[True] = True
    kind: Literal["fact", "change", "comparison", "causal", "attribution", "prediction"] = "fact"
    evidence_questions: list[str] = Field(min_length=1, max_length=3)
    queries: list[str] = Field(min_length=1, max_length=2)
    entities: list[str] = Field(default_factory=list, max_length=8)
    jurisdiction: str | None = Field(default=None, max_length=150)
    time_scope: str | None = Field(default=None, max_length=300)
    population: str | None = Field(default=None, max_length=300)
    metric: str | None = Field(default=None, max_length=200)
    negated: bool = False
    modality: Literal["asserted", "possible", "hypothetical", "question"] = "asserted"
    attribution: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_bounded_questions(self):
        if any(not value.strip() or len(value) > 500 for value in self.evidence_questions):
            raise ValueError("Evidence questions must contain 1 to 500 characters.")
        if any(not value.strip() or len(value) > 300 for value in self.queries):
            raise ValueError("Search queries must contain 1 to 300 characters.")
        if any(not value.strip() or len(value) > 200 for value in self.entities):
            raise ValueError("Entities must contain 1 to 200 characters.")
        return self


class VerificationPlan(VerificationModel):
    version: Literal["verification-v1"] = "verification-v1"
    source_text: str = Field(min_length=1, max_length=5000)
    status: Literal["planned", "fallback"] = "planned"
    fallback_reason: Literal["provider_unavailable", "planner_timeout", "invalid_plan", "not_checkable"] | None = None
    assertions: list[VerificationAssertion] = Field(min_length=1, max_length=5)
    assumptions: list[str] = Field(default_factory=list, max_length=8)
    warnings: list[str] = Field(default_factory=list, max_length=8)
    as_of: date | None = None

    @model_validator(mode="after")
    def validate_grounded_assertions(self):
        if self.status != "fallback" and self.fallback_reason is not None:
            raise ValueError("Only a fallback plan can have a fallback reason.")
        if any(not value.strip() or len(value) > 300 for value in self.warnings):
            raise ValueError("Plan warnings must contain 1 to 300 characters.")
        ids = [item.id for item in self.assertions]
        if len(ids) != len(set(ids)):
            raise ValueError("Verification assertion IDs must be unique.")
        if not any(item.material for item in self.assertions):
            raise ValueError("A verification plan needs a material assertion.")
        for item in self.assertions:
            if item.text not in self.source_text:
                raise ValueError("Every assertion must be an exact span of the submitted text.")
            for value in [*item.entities, item.population, item.metric, item.attribution]:
                if value is not None and value not in self.source_text:
                    raise ValueError("Scope entities and attribution must be grounded in the input.")
        if self.status == "fallback" and (
            len(self.assertions) != 1 or self.assertions[0].text != self.source_text
        ):
            raise ValueError("Fallback must preserve the whole input without invented decomposition.")
        return self


class VerificationCitation(VerificationModel):
    evidence_id: str = Field(min_length=1, max_length=200)
    quote: str = Field(min_length=1, max_length=6000)


class VerificationScopeResolution(VerificationCitation):
    """A quoted explanation for admitting a source flagged at whole-claim scope."""

    explanation: str = Field(min_length=1, max_length=1500)


ScopeStatus = Literal["established", "not_applicable", "unknown", "different"]


class VerificationScopeChecks(VerificationModel):
    entity: ScopeStatus = "unknown"
    jurisdiction: ScopeStatus = "unknown"
    time: ScopeStatus = "unknown"
    population: ScopeStatus = "unknown"
    metric: ScopeStatus = "unknown"
    modality: ScopeStatus = "unknown"
    attribution: ScopeStatus = "unknown"


class VerificationMaterialCounterfact(VerificationCitation):
    """An explicit counterfact to a material clause within a causal assertion."""

    claim_span: str = Field(min_length=10, max_length=5000)
    explanation: str = Field(min_length=1, max_length=1500)
    scope_checks: VerificationScopeChecks

    @model_validator(mode="after")
    def validate_counterfact_scope(self):
        if any(value in {"unknown", "different"} for value in self.scope_checks.model_dump().values()):
            raise ValueError("A material counterfact requires established scope for its exact claim clause.")
        return self


class VerificationFinding(VerificationModel):
    assertion_id: str = Field(pattern=r"^a[1-5]$")
    status: Literal["supported", "contradicted", "unresolved", "conflicting"]
    citations: list[VerificationCitation] = Field(default_factory=list, max_length=10)
    explanation: str = Field(min_length=1, max_length=3000)
    basis: Literal["direct", "inference", "none"] = "none"
    scope: Literal["established", "unknown", "different"] = "unknown"
    scope_checks: VerificationScopeChecks = Field(default_factory=VerificationScopeChecks)
    scope_resolutions: list[VerificationScopeResolution] = Field(default_factory=list, max_length=10)
    evidence_adequacy: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False, strict=True)
    material_counterfact: VerificationMaterialCounterfact | None = None
    gaps: list[str] = Field(default_factory=list, max_length=12)
    repair_queries: list[str] = Field(default_factory=list, max_length=2)

    @model_validator(mode="after")
    def validate_decisive_finding(self):
        if self.material_counterfact is not None and self.status != "contradicted":
            raise ValueError("A material counterfact can only explain a contradicted assertion.")
        if self.status != "unresolved":
            if not self.citations or self.basis == "none" or self.scope != "established":
                raise ValueError("A decisive finding requires citations, a reasoning basis and established scope.")
            if any(value in {"unknown", "different"} for value in self.scope_checks.model_dump().values()):
                raise ValueError("A decisive finding cannot leave a scope requirement unresolved.")
        if any(not value.strip() or len(value) > 500 for value in self.gaps):
            raise ValueError("Verification gaps must contain 1 to 500 characters.")
        if any(not value.strip() or len(value) > 300 for value in self.repair_queries):
            raise ValueError("Repair queries must contain 1 to 300 characters.")
        return self


class VerificationAssessment(VerificationModel):
    version: Literal["verification-v1"] = "verification-v1"
    method: Literal["joint_evidence", "specialist"] = "joint_evidence"
    findings: list[VerificationFinding] = Field(min_length=1, max_length=5)
    rationale: str = Field(min_length=1, max_length=4000)
    repair_queries: list[str] = Field(default_factory=list, max_length=2)
    repair_attempted: bool = False
    repair_status: Literal["not_needed", "attempted", "improved", "unchanged", "no_new_evidence", "unavailable", "budget_exhausted"] = "not_needed"

    @model_validator(mode="after")
    def validate_unique_findings(self):
        ids = [item.assertion_id for item in self.findings]
        if len(ids) != len(set(ids)):
            raise ValueError("Each assertion must have one combined verification finding.")
        if any(not value.strip() or len(value) > 300 for value in self.repair_queries):
            raise ValueError("Repair queries must contain 1 to 300 characters.")
        if self.repair_attempted != (self.repair_status not in {"not_needed", "budget_exhausted"}):
            raise ValueError("Repair status must agree with whether a repair was attempted.")
        return self


def causal_fact_spans(text: str) -> set[str]:
    """Complete event/premise clauses for one explicit, unambiguous connector.

    This is a conservative boundary check, not semantic decomposition. Temporal
    'since', fronted causes, and multiple links need a separately validated plan.
    """
    if re.search(r"\b(?:or|either|if|unless)\b", text, re.I):
        return set()  # A false constituent cannot generally refute a disjunction/conditional.
    markers = list(re.finditer(
        r"\b(?:because(?:\s+of)?|due\s+to|owing\s+to|as\s+a\s+result\s+of|as\s+a\s+consequence\s+of|on\s+account\s+of|caused\s+by)\b",
        text, re.I,
    ))
    if len(markers) != 1:
        return set()
    marker = markers[0]
    parts = [part.strip(" \t\r\n.,;:!?") for part in (text[:marker.start()], text[marker.end():])]
    return set(parts) if all(parts) else set()


def validate_verification_provenance(
    assessment: VerificationAssessment,
    plan: VerificationPlan,
    sources: Mapping[str, object],
) -> None:
    """Validate against the actual supplied/stored passages, never model memory."""
    expected = {item.id for item in plan.assertions}
    actual = {item.assertion_id for item in assessment.findings}
    if actual != expected:
        raise ValueError("Verification findings must cover exactly the planned assertions.")
    for finding in assessment.findings:
        cited_ids = {item.evidence_id for item in finding.citations}
        counterfact = finding.material_counterfact
        if counterfact:
            assertion = next(item for item in plan.assertions if item.id == finding.assertion_id)
            if (assertion.kind != "causal" or counterfact.claim_span not in assertion.text
                    or counterfact.claim_span.strip(" \t\r\n.,;:!?") not in causal_fact_spans(assertion.text)):
                raise ValueError("A material counterfact must identify an exact clause in the causal assertion.")
            if counterfact.evidence_id not in cited_ids:
                raise ValueError("A material counterfact must cite evidence used for the same assertion.")
        for resolution in finding.scope_resolutions:
            if resolution.evidence_id not in cited_ids:
                raise ValueError("A scope resolution must refer to evidence cited for the same assertion.")
        for citation in [*finding.citations, *finding.scope_resolutions, *([counterfact] if counterfact else [])]:
            source = sources.get(citation.evidence_id)
            passage = source.get("passage", "") if isinstance(source, dict) else getattr(source, "passage", "")
            if source is None or citation.quote not in passage:
                raise ValueError("Verification citations must quote their supplied evidence passage exactly.")
        if finding.status != "unresolved":
            resolved_ids = {item.evidence_id for item in finding.scope_resolutions}
            for evidence_id in cited_ids:
                source = sources[evidence_id]
                provenance = source.get("provenance") if isinstance(source, dict) else getattr(source, "provenance", None)
                applicability = provenance.get("applicability") if isinstance(provenance, dict) else getattr(provenance, "applicability", None)
                if applicability == "different_scope" and evidence_id not in resolved_ids:
                    raise ValueError("A flagged source needs a quoted resolution of its scope for this assertion.")


def validate_plan_input(plan: VerificationPlan, original_text: str, extracted_claim: str | None) -> None:
    """Use the input stage's exact Unicode rules, not semantic rewriting."""
    from ..input_preparation.service import _normalise_characters
    normalise = lambda value: _normalise_characters(value or "")[0]
    if normalise(plan.source_text) not in {normalise(original_text), normalise(extracted_claim)}:
        raise ValueError("Verification source text must match the submitted or extracted claim.")


def verification_outcome(assessment: VerificationAssessment) -> str:
    statuses = {finding.status for finding in assessment.findings}
    if "contradicted" in statuses:
        return "contradicted"
    if "conflicting" in statuses:
        return "conflicting"
    if statuses == {"supported"}:
        return "supported"
    return "insufficient_evidence"


def verification_proof_quality(finding: VerificationFinding, sources: Mapping[str, object]) -> float:
    """One argument's strength is bounded by its weakest source and adequacy."""
    from ..evidence_assessment.service import SOURCE_BASE_LIMITS
    if finding.evidence_adequacy is None:
        raise ValueError("A decisive joint proof requires recorded evidence adequacy.")
    source_caps = []
    for citation in finding.citations:
        source = sources[citation.evidence_id]
        source_type = source.get("source_type") if isinstance(source, dict) else source.source_type
        source_caps.append(SOURCE_BASE_LIMITS[source_type])
    if not source_caps:
        raise ValueError("A decisive joint proof requires cited sources.")
    quality = min(*source_caps, finding.evidence_adequacy, .70 if finding.basis == "inference" else .90,
                  .89 if finding.material_counterfact else 1.0)
    if quality < .60:
        raise ValueError("A decisive joint proof cannot fall below the admissible evidence floor.")
    return quality


def verification_decision(assessment: VerificationAssessment, sources: Mapping[str, object]) -> tuple[str, list[dict]]:
    """Return the whole-message outcome and one proof vote per relevant stance.

The same helper is used by assembly and final contract validation. More links
within one proof never create an independence/corroboration bonus.
"""
    outcome = verification_outcome(assessment)
    findings = assessment.findings
    selected = ([item for item in findings if item.status == "contradicted"] if outcome == "contradicted"
                else [item for item in findings if item.status == "conflicting"] if outcome == "conflicting"
                else findings if outcome == "supported" else [])
    if not selected:
        return outcome, []
    chosen = (min(selected, key=lambda item: verification_proof_quality(item, sources)) if outcome == "supported"
              else max(selected, key=lambda item: verification_proof_quality(item, sources)))
    quality = verification_proof_quality(chosen, sources)
    if outcome == "contradicted" and any(item.status == "unresolved" for item in findings):
        quality = min(quality, .89)
    stances = ["contradicting"] if outcome == "contradicted" else ["supporting", "contradicting"] if outcome == "conflicting" else ["supporting"]
    citation = chosen.citations[0]
    return outcome, [{
        "evidence_id": citation.evidence_id, "stance": stance, "quality_score": quality,
        "assessment_reason": chosen.explanation, "evidence_quote": citation.quote,
    } for stance in stances]


def validate_verification_result(result, sources: Mapping[str, object] | None = None) -> None:
    """A joint proof cannot be saved with a contradictory label or inflated score."""
    assessment = result.verification
    if assessment is None or assessment.method != "joint_evidence":
        return
    expected = verification_outcome(assessment)
    if result.assessment_outcome != expected:
        raise ValueError("The result outcome must match its joint verification findings.")
    for finding in assessment.findings:
        if finding.status != "unresolved" and (
            finding.evidence_adequacy is None or finding.evidence_adequacy < .60
        ):
            raise ValueError("A decisive joint proof requires admissible evidence adequacy.")
    if sources is None:
        return
    from ..evidence_assessment.scoring import score_evidence
    from .models import AssessedEvidence
    _, votes = verification_decision(assessment, sources)
    scored_outcome, score, summary = score_evidence([AssessedEvidence(**vote) for vote in votes], sources)
    if (scored_outcome != expected or result.misinformation_risk_score != score or result.scoring is None
            or result.scoring.model_dump(exclude={"reasons"}) != summary.model_dump(exclude={"reasons"})):
        raise ValueError("The result score must match the verified proof strength and source limits.")
