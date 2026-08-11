from uuid import uuid4

from app.schemas import TextAnalysisResult


def analyse_text_content(
    text: str
) -> TextAnalysisResult:
    return TextAnalysisResult(
        result_id=str(uuid4()),
        extracted_claim=text,
        concern_label="Needs Caution",
        misinformation_risk_score=50,
        uncertainty="High",
        explanation=(
            "This is a mock analysis result. "
            "Real misinformation analysis has "
            "not been implemented yet."
        ),
        evidence=[]
    )