# app/services/affiliate_search.py
from typing import List, Dict, Any

async def do_affiliate_search(search_query: str) -> List[Dict[str, Any]]:
    if "stofzuiger" not in search_query.lower():
        return []

    return [
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
