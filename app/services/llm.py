from app.chat_engine.llm import call_yellowmind_llm
from typing import Tuple, Dict, Any
from app.chat_engine.prompts import (
    SYSTEM_PROMPT_CHAT,
    SYSTEM_PROMPT_SEARCH,
)

def run_llm(
    question: str,
    language: str,
    kb_answer: str | None,
    sql_match: dict | None,
    hints: dict,
    history: list[dict],
) -> Tuple[str, Dict[str, Any]]:
    """
    Roept YellowMind LLM aan en valideert het resultaat.
    """

    final_answer, raw_output = call_yellowmind_llm(
        question=question,
        language=language,
        kb_answer=kb_answer,
        sql_match=sql_match,
        hints=hints,
        history=history,
    )

    if not final_answer:
        final_answer = "⚠️ Geen geldig antwoord beschikbaar."

    return final_answer, raw_output
