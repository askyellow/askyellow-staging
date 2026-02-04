import os
import requests

from fastapi import APIRouter, HTTPException

router = APIRouter()

# ---- Websearch Tool (Serper) ----
SERPER_API_KEY = os.getenv("SERPER_API_KEY")

@router.post("/tool/websearch")
async def tool_websearch(payload: dict):
    """Proxy naar Serper API voor webresultaten."""
    query = (payload.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query missing")

    if not SERPER_API_KEY:
        raise HTTPException(status_code=500, detail="SERPER_API_KEY ontbreekt op de server")

    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json",
    }
    body = {"q": query}

    try:
        r = requests.post(url, json=body, headers=headers, timeout=10)
        data = r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Websearch error: {e}")

    results = []
    for item in data.get("organic", [])[:4]:
        results.append({
            "title": item.get("title"),
            "snippet": item.get("snippet"),
            "url": item.get("link"),
        })

    return {
        "tool": "websearch",
        "query": query,
        "results": results,
    }