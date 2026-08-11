from fastapi import APIRouter

from app.schemas import (
    TextAnalysisRequest,
    TextAnalysisResult,
)
from app.services.analysis_service import (
    analyse_text_content,
)


router = APIRouter(
    prefix="/analysis",
    tags=["Analysis"]
)


@router.post(
    "/text",
    response_model=TextAnalysisResult
)
def analyse_text(
    request: TextAnalysisRequest
):
    return analyse_text_content(request.text)