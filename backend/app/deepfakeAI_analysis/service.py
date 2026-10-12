import io
import os
import logging
import json
from pathlib import Path

from PIL import Image
from dotenv import load_dotenv
from google import genai
from google.genai import types

from app.deepfakeAI_analysis.score_service import score_deepfakeAI

logger = logging.getLogger(__name__)

# --------------------------------------------------
# Paths
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parents[2]

# --------------------------------------------------
# Gemini API configuration
# --------------------------------------------------

load_dotenv(ROOT_DIR / ".env")

API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=API_KEY)

GEMINI_MODEL = "gemini-3.5-flash-lite"

# --------------------------------------------------
# Generic output for uncertain results
# --------------------------------------------------

UNCERTAIN_EXPLANATION = (
    "The analysis is uncertain because the detection systems "
    "produced inconclusive or conflicting results. Image quality, "
    "resolution, or compression may affect detection accuracy. "
)


def make_uncertain_result():
    return {
        "label": "Uncertain",
        "confidence": None,
        "real_probability": None,
        "fake_probability": None,
        "explanation": {
            "visual_evidence": None,
            "reasoning": UNCERTAIN_EXPLANATION,
            "limitations": None,
        },
    }

# --------------------------------------------------
# Gemini prompt
# --------------------------------------------------

GEMINI_PROMPT = """
You are assisting with AI-generated image / AI deepfake detection.

You will receive:
1. An image to analyse.
2. The prediction and confidence scores produced by a
   specialised AI-image detector.

Perform your own visual assessment of the image first.
Then consider the detector's prediction and confidence scores
as additional evidence.

Return a single valid JSON object. Do not include Markdown
code fences, introductory text, or anything outside the JSON.

Use exactly this structure:

{
  "assessment": "Real",
  "agreement": "Agree",
  "visual_evidence": [
    "Describe a visible observation relevant to the assessment."
  ],
  "reasoning": "Explain your assessment and how it compares with the detector's prediction.",
  "limitations": "Explain the important limitations of this assessment."
}

Field requirements:

- "assessment" must be exactly one of:
  "Real", "AI-generated/AI-deepfake", "Uncertain"

- "agreement" must be exactly one of:
  "Agree", "Disagree", "Uncertain"

- "visual_evidence" must be an array of strings.
  Return an empty array if there is no meaningful visual evidence.

- "reasoning" must be a string.

- "limitations" must be a string.

Assessment guidelines:

1. Make your own visual assessment before weighing the detector.
2. Do not automatically accept or reject the detector's prediction.
3. High detector confidence is not proof of correctness.
4. Do not claim to know how the detector reached its prediction.
5. Do not invent visual evidence.
6. If the evidence is insufficient, choose "Uncertain".
7. Use "Agree" when your assessment supports the detector's class.
8. Use "Disagree" when your assessment supports the opposite class.
9. Use "Uncertain" when you cannot meaningfully determine whether
   the detector is correct.
10. Return valid JSON with double-quoted keys and string values.
    Do not include trailing commas or comments.
"""

GEMINI_FIELDS = {
    "assessment",
    "agreement",
    "visual_evidence",
    "reasoning",
    "limitations",
}

# --------------------------------------------------
# Run Gemini vision assessment
# --------------------------------------------------

def analyse_with_gemini(image: Image.Image, detector_result: dict) -> dict:
    if client is None:
        raise RuntimeError(
            "Gemini API is unavailable because GEMINI_API_KEY is not configured."
        )
    
    # The production service receives a PIL image, not a file path.
    # Encode it in memory so no uploaded image needs to be saved.
    image_buffer = io.BytesIO()

    image.convert("RGB").save(image_buffer, format="JPEG")
    image_bytes = image_buffer.getvalue()

    image_part = types.Part.from_bytes(
        data=image_bytes,
        mime_type="image/jpeg",
    )

    detector_context = f"""
Existing detector results:

Prediction: {detector_result['label']}
Confidence: {detector_result['confidence']:.4f}
Real probability: {detector_result['real_probability']:.4f}
Fake probability: {detector_result['fake_probability']:.4f}

Analyse the attached image using these results as additional
evidence, not as ground truth.
"""

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            GEMINI_PROMPT,
            detector_context,
            image_part,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )

    if not response.text:
        raise ValueError("Gemini returned an empty response.")

    result = json.loads(response.text)

    # Validate the required fields.
    if not isinstance(result, dict):
        raise ValueError("Gemini response must be a JSON object.")

    if set(result) != GEMINI_FIELDS:
        raise ValueError(
            "Gemini response contains missing or unexpected fields."
        )

    if result.get("assessment") not in {
        "Real",
        "AI-generated/AI-deepfake",
        "Uncertain",
    }:
        raise ValueError("Invalid Gemini assessment.")

    if result.get("agreement") not in {
        "Agree",
        "Disagree",
        "Uncertain",
    }:
        raise ValueError("Invalid Gemini agreement value.")

    evidence = result["visual_evidence"]

    if not isinstance(evidence, list) or not all(
        isinstance(item, str) for item in evidence
    ):
        raise ValueError(
            "visual_evidence must be an array of strings."
        )

    for field in ("reasoning", "limitations"):
        if (
            not isinstance(result[field], str)
            or not result[field].strip()
        ):
            raise ValueError(
                f"Gemini field {field!r} must be a non-empty string."
            )

    return result


# --------------------------------------------------
# Compare detector and Gemini results
# --------------------------------------------------

def final_result(detector_result: dict, gemini_result: dict) -> dict:
    """
    Produce the final result.

    The detector's prediction and scores are accepted only if:
    1. Gemini explicitly reports agreement.
    2. Gemini's assessment matches the detector's prediction.

    Any disagreement or uncertainty produces an Uncertain result.
    """

    detector_label = detector_result["label"]

    # Map Gemini's assessment to the detector's label vocabulary.
    assessment_to_label = {
        "Real": "Real",
        "AI-generated/AI-deepfake": "Fake",
        "Uncertain": "Uncertain",
    }

    gemini_label = assessment_to_label[gemini_result["assessment"]]

    models_agree = (
        gemini_result["agreement"] == "Agree"
        and gemini_label == detector_label
    )

    if not models_agree:
        return make_uncertain_result()

    # Both systems agree on the predicted class.
    return {
        "label": detector_label,
        "confidence": detector_result["confidence"],
        "real_probability": detector_result["real_probability"],
        "fake_probability": detector_result["fake_probability"],
        "explanation": {
            "visual_evidence": gemini_result["visual_evidence"],
            "reasoning": gemini_result["reasoning"],
            "limitations": gemini_result["limitations"],
        },
    }

# ---------------------------------------------------------
# Complete analysis service
# ---------------------------------------------------------

def analyse_deepfakeAI(image: Image.Image) -> dict:
    """
    Analyse an image using the detector scoring service,
    Gemini assessment and perform result comparison to
    determine the final result.

    This function acts as the main entry point for the
    deepfake/AI image analysis pipeline.

    Detector failures propagate to the existing router error
    handling. Gemini failures produce the prototype's generic
    Uncertain result.
    """

    detector_result = score_deepfakeAI(image)

    try:
        gemini_result = analyse_with_gemini(image, detector_result)

    except Exception as exc:
        # Authentication/configuration failures must fail the analysis.
        # Do not misrepresent them as an uncertain classification.
        error_code = getattr(exc, "code", None)
        if (
            isinstance(exc, RuntimeError)
            or error_code in {400, 401, 403}
        ):
            logger.exception(
                "Gemini configuration or authentication failed."
            )
            raise

        logger.exception(
            "Gemini assessment failed; returning an uncertain result."
        )
        return make_uncertain_result()
    
    return final_result(detector_result, gemini_result)