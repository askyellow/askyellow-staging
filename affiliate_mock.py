# affiliate_mock.py
from typing import List, Dict, Any
import random

def load_mock_affiliate_products(search_query: str) -> List[Dict[str, Any]]:
    base_products = [
        {
            "title": "Philips PowerGo Stofzuiger met Zak",
            "price": 179,
            "type": "sledestofzuiger",
            "bag": True,
            "keywords": ["stofzuiger", "met zak", "laminaat"]
        },
        {
            "title": "Dyson V8 Absolute Steelstofzuiger",
            "price": 399,
            "type": "steelstofzuiger",
            "bag": False,
            "keywords": ["stofzuiger", "snoerloos", "krachtig"]
        },
        {
            "title": "iRobot Roomba i3+ Robotstofzuiger",
            "price": 499,
            "type": "robotstofzuiger",
            "bag": True,
            "keywords": ["robot", "stofzuiger", "laminaat"]
        },
        {
            "title": "Rowenta Compact Power Cyclonic",
            "price": 129,
            "type": "sledestofzuiger",
            "bag": False,
            "keywords": ["stofzuiger", "compact"]
        },
        {
            "title": "Philips SpeedPro Max",
            "price": 329,
            "type": "steelstofzuiger",
            "bag": False,
            "keywords": ["stofzuiger", "snoerloos", "zuigkracht"]
        },
    ]

    products: List[Dict[str, Any]] = []

    for i in range(50):
        p = random.choice(base_products)
        products.append({
            "source": "bol",
            "external_id": f"mock-{i}",
            "title": p["title"],
            "price": p["price"] + random.randint(-50, 50),
            "type": p["type"],
            "bag": p["bag"],
            "keywords": p["keywords"],
            "affiliate_url": f"https://bol.com/mock/{i}",
            "raw": p
        })

    return products
