"""One authoritative assessment, mapped to app results without another model.

Scope and local limitations are assessment inputs to validation. The public
result retains the existing schema; its decisions and explanatory text are
copied from this validated assessment rather than independently reclassified.
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.pipeline.shared.web_research import (
    ResearchAssessment,
    ResearchDraft,
    ResearchFinding,
    ResearchSource,
    ResearchVerdict,
)


class FindingScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_scope: str = Field(min_length=1, max_length=1500, description=(
        "The ORIGINAL assertion's population, location, period and comparison. "
        "State missing details instead of inventing a broader or narrower assertion."))
    evidence_scope: str = Field(min_length=1, max_length=1500, description=(
        "The population, period, definitions and comparison actually covered by the cited evidence."))
    applicability: Literal["exact", "qualified", "mismatch", "unknown"] = Field(description=(
        "exact: evidence applies to this assertion; qualified: an explained, limited inference "
        "still applies to this assertion; mismatch: it concerns a different population, period "
        "or comparison; unknown: applicability cannot be established. A narrower counterfact "
        "does not by itself contradict the broader original assertion."))
    reason: str = Field(min_length=1, max_length=1500, description=(
        "Explain why the evidence can or cannot establish this ORIGINAL assertion, "
        "including any limitation on the comparison."))

    @field_validator("claim_scope", "evidence_scope", "reason")
    @classmethod
    def nonblank_scope(cls, value):
        if not value.strip():
            raise PydanticCustomError("research_decision_scope_text_invalid", "Scope details cannot be blank.")
        return value


class DecisionFinding(ResearchFinding):
    status: Literal["supported", "contradicted", "mixed", "unresolved"] = Field(description=(
        "Your assessment of the ORIGINAL assertion after checking scope: supported; "
        "applicable evidence weighs against it (contradicted); credible conflict about "
        "this same assertion (mixed); or unresolved. Missing support alone is not contradiction."))
    explanation: str = Field(min_length=1, max_length=3000, description=(
        "Explain the final finding in plain English, including the evidence's applicability "
        "and qualifications. This text is copied to the app without another model rewriting it."))
    basis: Literal["direct", "bounded_inference", "unresolved"] = Field(default="direct", description=(
        "Use direct only for decisive evidence with exact applicability. Use bounded_inference "
        "for an explicitly justified applicable inference, and unresolved for unresolved findings."))
    scope: FindingScope
    limitations: list[str] = Field(default_factory=list, max_length=4, description=(
        "Limitations of this assertion's assessment, each 1 to 1000 characters. Required "
        "for bounded inferences. Across this and the overall list, use at most eight unique limitations."))

    @field_validator("limitations")
    @classmethod
    def valid_local_limits(cls, values):
        if any(not value.strip() or len(value) > 1000 for value in values):
            raise PydanticCustomError("research_decision_limitations_invalid", "Local limitations must contain 1 to 1000 characters.")
        return values

    @model_validator(mode="after")
    def scope_matches_decision(self):
        decisive = self.status != "unresolved"
        if self.scope.applicability in {"mismatch", "unknown"} and decisive:
            raise PydanticCustomError("research_scope_unresolved_required", "Mismatched or unknown evidence scope cannot establish a decisive finding.")
        if decisive and self.basis == "direct" and self.scope.applicability != "exact":
            raise PydanticCustomError("research_scope_direct_requires_exact", "Direct decisive evidence requires exact applicability to the assertion.")
        if decisive and self.scope.applicability == "qualified" and self.basis != "bounded_inference":
            raise PydanticCustomError("research_scope_qualified_requires_inference", "A qualified decisive finding requires a bounded inference.")
        if self.basis == "bounded_inference" and not self.limitations:
            raise PydanticCustomError("research_decision_local_limitations_required", "A bounded inference must state this finding's limitations.")
        return self


class DecisionDraft(ResearchDraft):
    """Structured assessment decisions; inherited consistency rules stay intact."""

    verdict: ResearchVerdict = Field(description=(
        "Choose the overall verdict AFTER assessing each original material assertion. "
        "It must agree with those findings; an unresolved cause cannot erase an established "
        "material contradiction. A provisional verdict in evidence notes is not binding."))
    summary: str = Field(min_length=1, max_length=4000, description=(
        "A concise, readable explanation of the final assessment and its qualifications."))
    findings: list[DecisionFinding] = Field(default_factory=list, max_length=8, description=(
        "Assess each original material assertion once, including its scope, status, reasoning "
        "basis and limitations. Background facts are explanations, not replacement assertions."))
    limitations: list[str] = Field(default_factory=list, max_length=8, description=(
        "Overall remaining uncertainty, each 1 to 1000 characters. Local limitations are "
        "also preserved here by the server. Use at most eight unique limitations in total."))

    @model_validator(mode="before")
    @classmethod
    def retain_local_limitations(cls, value):
        if not isinstance(value, dict):
            return value
        overall = value.get("limitations", [])
        findings = value.get("findings", [])
        if not isinstance(overall, list) or not isinstance(findings, list):
            return value
        # Leave malformed values for their field validators. Do not mutate the
        # caller's draft or silently discard a limitation to fit the app schema.
        if any(not isinstance(item, str) for item in overall):
            return value
        combined = list(dict.fromkeys(overall))
        for finding in findings:
            local = finding.get("limitations", []) if isinstance(finding, dict) else (
                finding.limitations if isinstance(finding, DecisionFinding) else [])
            if isinstance(local, list):
                for limitation in local:
                    if isinstance(limitation, str) and limitation not in combined:
                        combined.append(limitation)
        if len(combined) > 8:
            raise PydanticCustomError("research_decision_limitations_limit", "The combined assessment has more than eight unique limitations.")
        return {**value, "limitations": combined}

    @model_validator(mode="after")
    def distinct_original_assertions(self):
        claims = [" ".join(finding.claim.split()).casefold() for finding in self.findings]
        if len(set(claims)) != len(claims):
            raise PydanticCustomError("research_decision_duplicate_assertions", "Assess an original assertion once instead of duplicating it with different decisions.")
        return self


def bind_decision(
    draft: DecisionDraft,
    *,
    sources: Sequence[ResearchSource],
    as_of: date,
    model: str,
    research_text: str | None,
) -> ResearchAssessment:
    """Copy validated decisions into the existing result without reclassification.

    Revalidation also rejects a draft mutated after its initial construction.
    Final source-ID and verdict checks remain those of ResearchAssessment.
    """
    validated = DecisionDraft.model_validate(draft.model_dump(mode="python"))
    public_findings = [
        {name: getattr(finding, name) for name in ResearchFinding.model_fields}
        for finding in validated.findings
    ]
    return ResearchAssessment(
        verdict=validated.verdict,
        summary=validated.summary,
        findings=public_findings,
        limitations=list(validated.limitations),
        recommended_action=validated.recommended_action,
        sources=[source.model_dump(mode="python") for source in sources],
        as_of=as_of,
        model=model,
        research_text=research_text,
    )
