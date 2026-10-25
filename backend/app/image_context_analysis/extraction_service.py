import io
import os
import logging
import json
from pathlib import Path

from PIL import Image
from dotenv import load_dotenv
from google import genai
from google.genai import types

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
# Gemini caption extraction prompt
# --------------------------------------------------

GEMINI_PROMPT = """
You are extracting the caption of a social-media post from
a screenshot.

Identify the text that belongs to the post's caption and
transcribe it as accurately as possible. Then, extract the
main claim made in the caption.

Requirements:
1. Preserve the caption's original wording, spelling,
   punctuation, emojis, hashtags, and line breaks where possible.
2. Extract the main verifiable factual claim from the caption.
   Express it as a concise statement while preserving the
   original meaning. Do not introduce new facts.
3. Do not correct, rewrite, summarise, or fact-check the caption or the main claim.
4. Distinguish the post caption from usernames, timestamps,
   navigation elements, comments, likes, and other interface text.
5. Do not confuse text embedded in the photograph or image
   with the post caption.
6. If the caption continues behind a "more" button or is
   otherwise cut off, extract only the visible portion.
7. Do not invent text that is unclear or not visible.
8. If no post caption can be identified, set
   "extracted_caption" to an empty string and
   "main_claim" to an empty string.
9. If a caption is identified but contains no identifiable
   factual claim, preserve the caption in "extracted_caption"
   and set "main_claim" to an empty string.
10. Return a single valid JSON object without Markdown,
   code fences, or additional text.

Use exactly this structure:

{
  "extracted_caption": "The caption text, or an empty string.",
  "main_claim": "The main claim of the caption text, or an empty string."
}
"""

# --------------------------------------------------
# Expected Gemini response
# --------------------------------------------------

GEMINI_FIELDS = {"extracted_caption", "main_claim"}


# --------------------------------------------------
# Extract caption from a social-media screenshot
# --------------------------------------------------

def extract_caption(image: Image.Image) -> dict:
    """
    Extract a social-media post caption from a screenshot.

    The image is supplied as a PIL Image object. It is encoded
    in memory and is not saved to disk.

    Returns:
        {
            "status": "completed",
            "extracted_caption": "...",
            "main_claim": "..."
        }

    An empty extracted_caption means no identifiable caption
    was found. API and response-validation errors propagate
    to the caller for the router to handle.
    """

    if not isinstance(image, Image.Image):
        raise TypeError("image must be a PIL Image.Image object.")

    if not API_KEY:
        raise RuntimeError(
            "Gemini API is unavailable because GEMINI_API_KEY "
            "is not configured."
        )

    # Encode the image in memory; do not save the upload.
    image_buffer = io.BytesIO()
    image.convert("RGB").save(image_buffer, format="JPEG")
    image_bytes = image_buffer.getvalue()

    image_part = types.Part.from_bytes(
        data=image_bytes,
        mime_type="image/jpeg",
    )

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                GEMINI_PROMPT,
                image_part,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
    except Exception:
        logger.exception("Gemini caption extraction request failed.")
        raise

    if not response.text:
        raise ValueError("Gemini returned an empty response.")

    try:
        result = json.loads(response.text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(
            "Gemini returned an invalid JSON response."
        ) from exc

    if not isinstance(result, dict):
        raise ValueError("Gemini response must be a JSON object.")

    if set(result) != GEMINI_FIELDS:
        raise ValueError(
            "Gemini response contains missing or unexpected fields."
        )

    extracted_caption = result["extracted_caption"]
    main_claim = result["main_claim"]

    if not isinstance(extracted_caption, str):
        raise ValueError(
            "extracted_caption must be a string."
        )

    if not isinstance(main_claim, str):
        raise ValueError(
            "main_claim must be a string."
        )

    return {
        "status": "completed",
        "extracted_caption": extracted_caption,
        "main_claim": main_claim,
    }