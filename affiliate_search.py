# affiliate_search.py
from typing import List, Dict, Any
import logging
from affiliate.bol_client import BolClient
import os

from affiliate_mock import load_mock_affiliate_products

async def do_affiliate_search(
    search_query: str,
    session_id: str | None = None
):

    if not os.getenv("BOL_API_KEY"):
        logger.info(
            "[AFFILIATE_SEARCH] using mock data",
            extra={"session_id": session_id}
        )
        return load_mock_affiliate_products(search_query)

    # later: echte bol.com call

logger = logging.getLogger(__name__)

bol_client = BolClient(
client_id=os.getenv("BOL_API_KEY"),
client_secret=os.getenv("BOL_API_SECRET")
)


async def do_affiliate_search(
    search_query: str,
    session_id: str | None = None
) -> List[Dict[str, Any]]:

    logger.info(
        "[AFFILIATE_SEARCH] start",
        extra={
            "session_id": session_id,
            "search_query": search_query
        }
    )

    raw = await bol_client.search_products(
        query=search_query,
        limit=50
    )

    results: List[Dict[str, Any]] = []

    for p in raw.get("products", []):
        results.append({
            "source": "bol",
            "external_id": p.get("id"),
            "title": p.get("title"),
            "price": p.get("offerData", {}).get("offers", [{}])[0].get("price"),
            "brand": p.get("brand"),
            "categories": p.get("categoryTree", []),
            "url": p.get("url"),  # affiliate komt later
            "image": p.get("images", [{}])[0].get("url"),
            "raw": p  # 👈 goud voor later filteren
        })

    logger.info(
        "[AFFILIATE_SEARCH] done",
        extra={
            "session_id": session_id,
            "search_query": search_query,
            "result_count": len(results)
        }
    )

    return results
