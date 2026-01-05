from app.chat_engine.prompts import SYSTEM_PROMPT
from openai import OpenAI
import os

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

# =============================================================
# 6. OPENAI CALL — FIXED FOR o3 RESPONSE FORMAT (SAFE)
# =============================================================

def call_yellowmind_llm(
    question,
    language,
    kb_answer,
    sql_match,
    hints,
    history=None
):
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        }
    ]

    if history:
        for msg in history:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })

    messages.append({
        "role": "user",
        "content": question
    })

    print("=== PAYLOAD TO MODEL ===")
    for i, m in enumerate(messages):
        print(i, m["role"], m["content"][:80])
    print("========================")

    ai = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages
    )

    final_answer = ai.choices[0].message.content

    # 🔒 Airbag: verboden zinnen filteren
    BANNED_PHRASES = [
    "geen toegang",
    "geen toegang heb",
    "geen toegang heeft",
    "niet rechtstreeks opzoeken",
    "kan dat niet opzoeken",
    "kan dit niet opzoeken",
    "live websearch",
    "realtime websearch",
    "websearch",
    "internet",
    "online opzoeken",
    "als ai",
    "sorry",
]
    lower_answer = final_answer.lower()
    
    for phrase in BANNED_PHRASES:
        if phrase in final_answer.lower():
            final_answer = (
                "Ik help je hier graag bij. "
                "Kun je iets specifieker aangeven wat je zoekt?"
            )
            break

    return final_answer, []
