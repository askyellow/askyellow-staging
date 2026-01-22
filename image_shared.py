from fastapi import APIRouter, Request, HTTPException
from openai import OpenAI
from chat_shared import store_message_pair
import os
import re

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

router = APIRouter()


# =============================================================
# IMAGE INTENT DETECTION
# =============================================================

def wants_image(q: str) -> bool:
    triggers = [
        "genereer",
        "afbeelding",
        "plaatje",
        "beeld",
        "image",
        "illustratie",
    ]
    return any(t in q.lower() for t in triggers)

# -----------------------------
# IMAGE ROUTE
# -----------------------------
def generate_image(prompt: str) -> str:
    result = client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        size="1024x1024"
    )

    # 🔎 Log volledige response (tijdelijk)
    print("IMAGE RESPONSE:", result)

    # ✅ Veilig ophalen
    if result.data and len(result.data) > 0:
        image = result.data[0]

        # Sommige SDK's gebruiken .url, andere .b64_json
        if hasattr(image, "url") and image.url:
            return image.url

        if hasattr(image, "b64_json") and image.b64_json:
            return f"data:image/png;base64,{image.b64_json}"

    # ❌ Fallback
    return None

def detect_intent(text: str) -> str:
    if re.search(r"(afbeelding|image|plaatje|genereer|maak.*(afbeelding|image))", text, re.I):
        return "image"
    if re.search(r"(zoek|zoeken|opzoeken)", text, re.I):
        return "search"
    return "text"

# ===== IMAGE GENERATION AUTH CHECK =====
def require_auth_session(request: Request):
    # 👇 PRE-FLIGHT ALTIJD TOESTAAN
    if request.method == "OPTIONS":
        return

    session_id = request.headers.get("X-Session-Id") or ""
    if not session_id:
        raise HTTPException(
            status_code=403,
            detail="Login vereist voor image generation"
        )

    
    # if not user:
    #     raise HTTPException(
    #         status_code=403,
    #         detail="Ongeldige of verlopen sessie"
    #     )
    
    # image_shared.py

def handle_image_intent(
    session_id: str,
    question: str,
):
    image_url = generate_image(question)

    if not image_url:
        answer = "⚠️ Afbeelding genereren mislukt."
        store_message_pair(session_id, question, answer)
        return {"type": "error", "answer": answer}

    store_message_pair(session_id, question, f"[IMAGE]{image_url}")
    return {"type": "image", "url": image_url}
