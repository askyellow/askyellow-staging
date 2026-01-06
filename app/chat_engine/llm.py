from openai import OpenAI
import os

from app.chat_engine.time_context import build_time_context
from app.chat_engine.prompts import (
    SYSTEM_PROMPT_CHAT,
    SYSTEM_PROMPT_SEARCH,
)

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


# =============================================================
# 6. OPENAI CALL — FIXED FOR o3 RESPONSE FORMAT (SAFE)
# =============================================================

def run_llm(
    question,
    language,
    kb_answer,
    sql_match,
    hints,
    history=None,
    mode="chat",
):

    system_prompt = (
        SYSTEM_PROMPT_SEARCH
        if mode == "search"
        else SYSTEM_PROMPT_CHAT
)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": build_time_context()},
]


    MAX_HISTORY_MESSAGES = 8

    if history:
        for msg in history[-MAX_HISTORY_MESSAGES:]:            
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })

    messages.append({
        "role": "user",
        "content": question
    })

    print("=== PAYLOAD TO MODEL ===")
    total_chars = sum(len(m["content"]) for m in messages)        
    print(f"[LLM] total chars={total_chars} ~ tokens={total_chars//4}")

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
