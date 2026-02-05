# app/services/affiliate_search.py
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

async def do_affiliate_search(search_query: str) -> List[Dict[str, Any]]:
    logger.info(
        "[AFFILIATE_SEARCH] start",
        extra={
            "search_query": search_query
        }
    )

    results = [
        {
            "product_id": "bol_123",
            "title": "Philips Steelstofzuiger 3000 Series",
            "price": 179.00,
            "currency": "EUR",
            "specs": {
                "cordless": True,
                "max_price": 200,
                "floor_type": ["laminaat", "parket"],
                "suction_power": "hoog"
            },
            "shop": "bol",
            "product_url": "https://www.bol.com/nl/p/philips-3000"
        },
        {
            "product_id": "bol_456",
            "title": "Rowenta X-Pert 6.60",
            "price": 199.00,
            "currency": "EUR",
            "specs": {
                "cordless": True,
                "floor_type": ["laminaat"],
                "suction_power": "medium"
            },
            "shop": "bol",
            "product_url": "https://www.bol.com/nl/p/rowenta-xpert"
        }
    ]
    logger.info(
            "[AFFILIATE_SEARCH] done",
            extra={
                "search_query": search_query,
                "result_count": len(results)
            }
        )

    return results