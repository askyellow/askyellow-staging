# app/services/websearch_core.py
import os
from fastapi import APIRouter, HTTPException
from app.services.websearch_core import run_serper_search

SERPER_API_KEY = os.getenv("SERPER_API_KEY")

router = APIRouter()

def run_serper_search(query: str):
    query = (query or "").strip()
    if not query:
        return []

    if not SERPER_API_KEY:
        raise RuntimeError("SERPER_API_KEY ontbreekt op de server")

    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json",
    }
    body = {"q": query}

    r = requests.post(url, json=body, headers=headers, timeout=10)
    data = r.json()

    results = []
    for item in data.get("organic", [])[:4]:
        results.append({
            "title": item.get("title"),
            "snippet": item.get("snippet"),
            "url": item.get("link"),
        })

    return results

@router.post("/tool/websearch")
async def tool_websearch(payload: dict):
    query = (payload.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query missing")

    try:
        results = run_serper_search(query)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Websearch error: {e}")

    return {
        "tool": "websearch",
        "query": query,
        "results": results,
    }
