import os
import requests

SERPER_API_KEY = os.getenv("SERPER_API_KEY")

def web_search(query: str, limit: int = 4):
    if not SERPER_API_KEY or not query:
        return []

    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json",
    }
    body = {"q": query}

    r = requests.post(url, json=body, headers=headers, timeout=10)
    data = r.json()

    results = []
    for item in data.get("organic", [])[:limit]:
        results.append({
            "title": item.get("title"),
            "snippet": item.get("snippet"),
            "url": item.get("link"),
        })

    return results


# @app.post("/web")
#async def web_search(payload: dict):
#    query = payload.get("query", "")
#
#    prompt = f"""
#    Doe een webzoekopdracht naar echte websites die relevant zijn voor:
#    '{query}'.

#    Geef ALLEEN het volgende JSON-format terug:
#    [
#      {{"title": "Titel", "snippet": "Korte beschrijving", "url": "https://..."}},
#      ...
#    ]

#    Geen extra tekst, geen uitleg, geen markdown.
#    """

    # --- Nieuwe Responses API call ---
#    ai = client.responses.create(
#        model="gpt-4.1-mini",
#        input=[{"role": "user", "content": prompt}]
#    )

#    import json

#    raw_text = None

    # --- Extract content safely ---
#    for block in ai.output:
#        try:
#            if block.type == "message":
#                raw_text = block.content[0].text
#                break
#        except:
#            pass

#    if not raw_text:
#        return {"results": []}

    # --- Probeerslag 1: Direct JSON ---
#    try:
#        return {"results": json.loads(raw_text)}
#    except:
#        pass

    # --- Probeerslag 2: JSON tussen [...] halen ---
#    try:
#        start = raw_text.index("[")
#        end = raw_text.rindex("]") + 1
#        cleaned = raw_text[start:end]
#        return {"results": json.loads(cleaned)}
#    except:
#        pass

    # --- Fallback ---
#    return {
#        "results": [{
#            "title": "Webresultaten niet geformatteerd",
#            "snippet": raw_text[:250],
#            "url": ""
#        }]
##    }


#@app.post("/tool/websearch")
#async def tool_websearch(payload: dict):
#    """Proxy naar Serper API voor webresultaten."""
#    query = (payload.get("query") or "").strip()
#    if not query:
#        raise HTTPException(status_code=400, detail="Query missing")

#    if not SERPER_API_KEY:
#        raise HTTPException(status_code=500, detail="SERPER_API_KEY ontbreekt op de server")

#    url = "https://google.serper.dev/search"
#    headers = {
#        "X-API-KEY": SERPER_API_KEY,
#        "Content-Type": "application/json",
#    }
#    body = {"q": query}

#    try:
#        r = requests.post(url, json=body, headers=headers, timeout=10)
#        data = r.json()
#    except Exception as e:
#        raise HTTPException(status_code=500, detail=f"Websearch error: {e}")

#    results = []
#    for item in data.get("organic", [])[:4]:
#        results.append({
#            "title": item.get("title"),
#            "snippet": item.get("snippet"),
#            "url": item.get("link"),
#        })

#    return {
#        "tool": "websearch",
#        "query": query,
#        "results": results,
#    }

