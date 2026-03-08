from __future__ import annotations

import base64
import mimetypes
import os
import re
import tempfile
from typing import Optional

from fastapi import HTTPException, Request, UploadFile
from openai import OpenAI

from chat_shared import store_message_pair

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

VISION_MODEL = os.getenv("YM_VISION_MODEL", "gpt-4o-mini")
IMAGE_MODEL = os.getenv("YM_IMAGE_MODEL", "gpt-image-1")
MAX_UPLOAD_MB = int(os.getenv("UPLOAD_MAX_MB", "8"))

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


# =============================================================
# IMAGE INTENT DETECTION
# =============================================================

def wants_image(q: str) -> bool:
    q = (q or "").lower()
    triggers = [
        "genereer",
        "afbeelding",
        "plaatje",
        "beeld",
        "image",
        "illustratie",
        "maak een",
        "teken een",
    ]
    return any(t in q for t in triggers)


def detect_intent(text: str) -> str:
    text = text or ""

    if detect_uploaded_image_operation(text) == "edit":
        return "image_edit"

    if re.search(r"(afbeelding|image|plaatje|genereer|maak.*(afbeelding|image))", text, re.I):
        return "image"

    if re.search(r"(zoek|zoeken|opzoeken)", text, re.I):
        return "search"

    return "text"


def detect_uploaded_image_operation(text: str) -> str:
    """
    Bepaalt of een geüploade afbeelding geanalyseerd of bewerkt moet worden.
    """
    q = (text or "").lower().strip()

    edit_keywords = [
            "karikatuur",
            "cartoon",
            "strip",
            "stripstijl",
            "anime",
            "ghibli",
            "bewerk",
            "bewerken",
            "edit",
            "verander",
            "veranderen",
            "transformeer",
            "transformeren",
            "stijl",
            "pas aan",
            "achtergrond",
            "verwijder",
            "weghalen",
            "haal",
            "eruit halen",
            "uitknippen",
            "losmaken",
            "apart zetten",
            "apart in een afbeelding",
            "vrijstaand",
            "maak hiervan",
            "maak hier",
            "van maken",
        ]

    if any(k in q for k in edit_keywords):
        return "edit"

    return "analyze"


# =============================================================
# AUTH
# =============================================================

def require_auth_session(request: Request):
    if request.method == "OPTIONS":
        return

    session_id = request.headers.get("X-Session-Id") or ""
    if not session_id:
        raise HTTPException(
            status_code=403,
            detail="Login vereist voor image generation"
        )


# =============================================================
# VALIDATION / ENCODING
# =============================================================

async def read_and_validate_upload(upload: UploadFile) -> tuple[bytes, str]:
    if not upload:
        raise HTTPException(status_code=400, detail="Geen afbeelding ontvangen")

    content_type = (upload.content_type or "").lower().strip()
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Alleen JPG, PNG en WEBP zijn toegestaan"
        )

    data = await upload.read()
    if not data:
        raise HTTPException(status_code=400, detail="Leeg bestand")

    max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"Afbeelding te groot. Maximaal {MAX_UPLOAD_MB} MB"
        )

    return data, content_type


def bytes_to_data_url(data: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(data).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def normalize_generated_image_to_browser_src(image_obj) -> Optional[str]:
    if hasattr(image_obj, "b64_json") and image_obj.b64_json:
        return f"data:image/png;base64,{image_obj.b64_json}"

    if hasattr(image_obj, "url") and image_obj.url:
        return image_obj.url

    if isinstance(image_obj, dict):
        b64_json = image_obj.get("b64_json")
        if b64_json:
            return f"data:image/png;base64,{b64_json}"
        if image_obj.get("url"):
            return image_obj["url"]

    return None


# =============================================================
# TEXT → IMAGE
# =============================================================

def generate_image(prompt: str) -> str | None:
    result = client.images.generate(
        model=IMAGE_MODEL,
        prompt=prompt,
        size="1024x1024"
    )

    if result.data and len(result.data) > 0:
        return normalize_generated_image_to_browser_src(result.data[0])

    return None


def handle_image_intent(session_id: str, question: str):
    image_url = generate_image(question)

    if not image_url:
        answer = "⚠️ Afbeelding genereren mislukt."
        store_message_pair(session_id, question, answer)
        return {"type": "error", "answer": answer}

    store_message_pair(session_id, question, f"[IMAGE]{image_url}")
    return {"type": "image", "url": image_url}


# =============================================================
# UPLOADED IMAGE → ANALYZE
# =============================================================

def analyze_uploaded_image(
    *,
    image_bytes: bytes,
    mime_type: str,
    question: str,
    history: list[dict] | None = None,
) -> str:
    data_url = bytes_to_data_url(image_bytes, mime_type)

    messages = [
        {
            "role": "system",
            "content": (
                "Je bent YellowMind. "
                "Analyseer afbeeldingen praktisch, eerlijk en helder in het Nederlands. "
                "Verzin niets wat je niet echt kunt zien. "
                "Noem onzekerheid expliciet."
            ),
        }
    ]

    if history:
        for msg in history[-12:]:
            content = msg.get("content")
            if not isinstance(content, str):
                continue
            if content.startswith("[IMAGE]") or content.startswith("[USER_IMAGE]"):
                continue
            messages.append({
                "role": msg.get("role", "user"),
                "content": content[:1200]
            })

    user_prompt = (question or "").strip() or "Beschrijf deze afbeelding kort en praktisch."

    messages.append({
        "role": "user",
        "content": [
            {"type": "text", "text": user_prompt},
            {"type": "image_url", "image_url": {"url": data_url}},
        ],
    })

    ai = client.chat.completions.create(
        model=VISION_MODEL,
        messages=messages,
    )

    if ai.choices and ai.choices[0].message and ai.choices[0].message.content:
        return ai.choices[0].message.content

    return "⚠️ Ik kon de afbeelding niet goed analyseren."


# =============================================================
# UPLOADED IMAGE → EDIT / TRANSFORM
# =============================================================

def edit_uploaded_image(
    *,
    image_bytes: bytes,
    mime_type: str,
    prompt: str,
) -> str:
    suffix = ALLOWED_IMAGE_TYPES.get(mime_type) or mimetypes.guess_extension(mime_type) or ".png"

    with tempfile.NamedTemporaryFile(delete=True, suffix=suffix) as tmp:
        tmp.write(image_bytes)
        tmp.flush()

        with open(tmp.name, "rb") as image_file:
            result = client.images.edit(
                model=IMAGE_MODEL,
                image=image_file,
                prompt=prompt,
                size="1024x1024",
            )

    if not result.data:
        raise HTTPException(status_code=500, detail="Geen afbeelding teruggekregen van image edit")

    browser_src = normalize_generated_image_to_browser_src(result.data[0])
    if not browser_src:
        raise HTTPException(status_code=500, detail="Image edit gaf geen bruikbare output terug")

    return browser_src