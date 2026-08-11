from typing import Literal

from pydantic import BaseModel, Field


class TextAnalysisRequest(BaseModel):
    text: str = Field(
        min_length=1,
        max_length=5000
    )


class EvidenceItem(BaseModel):
    title: str
    url: str
    stance: Literal[
        "supporting",
        "contradicting",
        "neutral"
    ]


class TextAnalysisResult(BaseModel):
    result_id: str

    extracted_claim: str

    concern_label: Literal[
        "Low Concern",
        "Needs Caution",
        "High Concern",
        "Not Enough Information"
    ]

    misinformation_risk_score: int = Field(
        ge=0,
        le=100
    )

    uncertainty: Literal[
        "Low",
        "Medium",
        "High"
    ]

    explanation: str

    evidence: list[EvidenceItem]