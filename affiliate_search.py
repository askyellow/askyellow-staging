# affiliate_search.py
from typing import List, Dict, Any
import logging
from bol_client import BolClient
import os
from fastapi import APIRouter
router = APIRouter()
from affiliate_engine import generate_affiliate_models, build_amazon_search_link

from affiliate_mock import load_mock_affiliate_products
logger = logging.getLogger(__name__)

AMAZON_TAG = os.getenv("AMAZON_TAG", "askyellow-21")

USE_BOL_API = False  # 🔥 NU HARD UIT

async def do_affiliate_search(search_query: str, session_id: str | None = None):

    if not os.getenv("BOL_API_KEY") or not os.getenv("BOL_API_SECRET"):
        logger.info(
            "[AFFILIATE_SEARCH] bol api not available, using mock",
            extra={"session_id": session_id}
        )
        return load_mock_affiliate_products(search_query)

    # 👇 echte bol.com call (later)

from constraint_extractor import extract_and_normalize

@router.post("/affiliate/models")
def affiliate_models(data: dict):
    session_id = data.get("session_id")
    constraints_input = data.get("constraints")

    print("SESSION:", session_id)
    print("RAW CONSTRAINTS INPUT:", constraints_input)

    if not session_id or not constraints_input:
        return {"models": []}

    # 🔥 Stap 1: Query → structured constraints
    if isinstance(constraints_input, dict) and "query" in constraints_input:
        conversation_text = constraints_input["query"]
        structured = extract_and_normalize(conversation_text)
    else:
        structured = constraints_input

    print("STRUCTURED CONSTRAINTS:", structured)

    # 🔥 Stap 2: Structured → affiliate models
    models = generate_affiliate_models(structured, session_id)

    enriched = []
    for m in models:
        model_name = f"{m['brand']} {m['model']}"
        link = build_amazon_search_link(model_name, AMAZON_TAG)

        enriched.append({
            **m,
            "affiliate_url": link
        })

    return {"models": enriched}


# bol_client = BolClient(
# client_id=os.getenv("BOL_API_KEY"),
# client_secret=os.getenv("BOL_API_SECRET")
# )


# async def do_affiliate_search(
#     search_query: str,
#     session_id: str | None = None
# ) -> List[Dict[str, Any]]:

#     logger.info(
#         "[AFFILIATE_SEARCH] start",
#         extra={
#             "session_id": session_id,
#             "search_query": search_query
#         }
#     )

#     raw = await bol_client.search_products(
#         query=search_query,
#         limit=50
#     )

#     results: List[Dict[str, Any]] = []

#     for p in raw.get("products", []):
#         results.append({
#             "source": "bol",
#             "external_id": p.get("id"),
#             "title": p.get("title"),
#             "price": p.get("offerData", {}).get("offers", [{}])[0].get("price"),
#             "brand": p.get("brand"),
#             "categories": p.get("categoryTree", []),
#             "url": p.get("url"),  # affiliate komt later
#             "image": p.get("images", [{}])[0].get("url"),
#             "raw": p  # 👈 goud voor later filteren
#         })

#     logger.info(
#         "[AFFILIATE_SEARCH] done",
#         extra={
#             "session_id": session_id,
#             "search_query": search_query,
#             "result_count": len(results)
#         }
#     )

#     return results
