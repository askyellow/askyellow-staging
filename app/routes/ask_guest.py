from fastapi import APIRouter, Request
from app.services.llm import run_llm
from app.context import build_context

router = APIRouter()

@router.post("/ask/guest")
async def ask_guest(request: Request):
    data = await request.json()
    question = (data.get("question") or "").strip()
    language = (data.get("language") or "nl").lower()

    if not question:
        return {"error": "No question"}

    context = build_context(question, language)

    answer, _ = run_llm(
        question=question,
        language=language,
        kb_answer=context["kb_answer"],
        sql_match=context["sql_match"],
        hints=[],
        history=[],
        mode="guest",
    )

    return {"answer": answer}
