import os
import re
import requests
from fastapi import HTTPException

# =============================================================
# SHOPIFY FUNCTIONS
# =============================================================

SHOPIFY_API_VERSION = "2025-10"

def shopify_get_products():
    url = f"https://{os.getenv('SHOPIFY_STORE_URL')}/admin/api/{SHOPIFY_API_VERSION}/products.json?limit=20"
    headers = {
        "X-Shopify-Access-Token": os.getenv("SHOPIFY_ACCESS_TOKEN")
    }
    response = requests.get(url, headers=headers)
    return response.json()
def shopify_search_products(query: str):
    url = f"https://{os.getenv('SHOPIFY_STORE_URL')}/admin/api/{SHOPIFY_API_VERSION}/products.json"
    headers = {"X-Shopify-Access-Token": os.getenv("SHOPIFY_ACCESS_TOKEN")}

    response = requests.get(url, headers=headers)
    data = response.json()

    query = query.lower()
    results = []

    for product in data.get("products", []):

        # Skip concept + archived products
        if product.get("status") != "active":
            continue

        title = product.get("title", "").lower()
        body = product.get("body_html", "").lower()
        tags = " ".join(product.get("tags", [])).lower()

        # match rules
        if query not in title and query not in body and query not in tags:
            continue

        variants = product.get("variants", [])
        main_variant = variants[0] if variants else {}

        price = float(main_variant.get("price", 0) or 0)
        compare_at = float(main_variant.get("compare_at_price") or 0)

        on_sale = compare_at > price
        discount_pct = 0
        if on_sale:
            discount_pct = int(((compare_at - price) / compare_at) * 100)

        inventory = main_variant.get("inventory_quantity", 0)

        if inventory <= 0:
            stock_status = "out"
        elif inventory == 1:
            stock_status = "low"
        elif inventory < 10:
            stock_status = "medium"
        else:
            stock_status = "in"

        results.append({
            "id": product.get("id"),
            "title": product.get("title"),
            "handle": product.get("handle"),
            "price": price,
            "compare_at": compare_at,
            "on_sale": on_sale,
            "discount_pct": discount_pct,
            "image": product.get("image", {}).get("src") if product.get("image") else None,
            "variants_count": len(variants),
            "stock_status": stock_status,
            "inventory": inventory,
	        "created_at": product.get("created_at")
        })

    # --- SORT: newest first (based on Shopify "created_at") ---
    results.sort(key=lambda p: p.get("created_at", ""), reverse=True)

    return results

# @app.get("/shopify/search")
# def shopify_search(q: str):
#    return shopify_search_products(q)

# ---- Shopify Search Tool 2.0 (title + body + tags + fuzzy) ----
SHOPIFY_STORE = os.getenv("SHOPIFY_STORE_URL")
SHOPIFY_ADMIN_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")


def _extract_search_tokens(query: str) -> set:
    """Zet de gebruikersvraag om in zoektokens + extra kerst/cadeau hints."""
    q = (query or "").lower()
    # basis: woorden
    tokens = set(re.findall(r"[a-z0-9]+", q))

    # fuzzy extras
    if "kerst" in q:
        tokens.add("kerst")
    if "christmas" in q:
        tokens.add("kerst")
        tokens.add("christmas")
    if "cadeau" in q or "kado" in q:
        tokens.update(["cadeau", "gift"])
    if "gift" in q:
        tokens.add("cadeau")

    return tokens


def _score_shopify_product(product: dict, tokens: set) -> int:
    """Geeft een relevanciescore op basis van title, beschrijving, tags, type."""
    title = (product.get("title") or "").lower()
    body = (product.get("body_html") or "").lower()
    tags_raw = (product.get("tags") or "") or ""
    tags = " ".join([t.strip().lower() for t in tags_raw.split(",") if t.strip()])
    ptype = (product.get("product_type") or "").lower()

    combined = " ".join([title, body, tags, ptype])
    score = 0

    for tok in tokens:
        if not tok:
            continue
        if tok in title:
            score += 8
        if tok in tags:
            score += 5
        if tok in ptype:
            score += 3
        if tok in body:
            score += 2

    # extra boost voor kerstproducten
    if "kerst" in tokens and "kerst" in combined:
        score += 10

    return score


# @app.post("/tool/shopify_search")
# async def tool_shopify_search(payload: dict):
#    """Slimme zoektool voor de AskYellow Shopify shop.

#   - Zoekt in title, description (body_html), tags en product_type
#    - Fuzzy handling van 'kerstcadeau', 'cadeau', 'gift', etc.
#    - Sorteert op relevatie + recentheid
#    - Fallback: altijd maximaal 5 producten
#    """
#   query = (payload.get("query") or "").strip()
#    if not query:
#        raise HTTPException(status_code=400, detail="Missing query")

#    if not SHOPIFY_STORE or not SHOPIFY_ADMIN_TOKEN:
#        raise HTTPException(status_code=500, detail="Shopify env vars ontbreken")

#    url = f"https://{SHOPIFY_STORE}/admin/api/2025-10/products.json?limit=250"
#    headers = {"X-Shopify-Access-Token": SHOPIFY_ADMIN_TOKEN}

#    try:
#        r = requests.get(url, headers=headers, timeout=15)
#        data = r.json()
#    except Exception as e:
#        raise HTTPException(status_code=500, detail=f"Shopify error: {e}")

#    products = data.get("products", []) or []
#    tokens = _extract_search_tokens(query)

#    scored = []
#    for p in products:
#        # alleen actieve producten
#        if p.get("status") != "active":
#            continue

#        score = _score_shopify_product(p, tokens)
#        if score <= 0:
#            continue

#        variants = p.get("variants") or []
#        main_variant = variants[0] if variants else {}
#        price = main_variant.get("price")
#        compare_at = main_variant.get("compare_at_price")

#        try:
#            price_f = float(price or 0)
#        except Exception:
#            price_f = 0.0
#        try:
#            compare_f = float(compare_at or 0)
#        except Exception:
#            compare_f = 0.0

#        on_sale = compare_f > price_f
#        discount_pct = 0
#        if on_sale and compare_f:
#            discount_pct = int(((compare_f - price_f) / compare_f) * 100)

#        result = {
#            "id": p.get("id"),
#            "title": p.get("title"),
#            "handle": p.get("handle"),
#            "url": f"https://shop.askyellow.nl/products/{p.get('handle')}",
#            "image": (p.get("image") or {}).get("src"),
#            "price": price_f if price_f else None,
#            "compare_at": compare_f if compare_f else None,
#            "discount_pct": discount_pct or None,
#            "created_at": p.get("created_at") or "",
#            "score": score,
#        }
#        scored.append(result)

    # Fallback: als niets gescoord heeft, toon dan gewoon de laatste producten
#    if not scored:
#        for p in products:
#            if p.get("status") != "active":
#                continue
#            variants = p.get("variants") or []
#            main_variant = variants[0] if variants else {}
#            price = main_variant.get("price")
#            compare_at = main_variant.get("compare_at_price")

#            try:
#                price_f = float(price or 0)
#            except Exception:
#                price_f = 0.0
#            try:
#                compare_f = float(compare_at or 0)
#            except Exception:
#                compare_f = 0.0

#            result = {
#                "id": p.get("id"),
#                "title": p.get("title"),
#                "handle": p.get("handle"),
#                "url": f"https://shop.askyellow.nl/products/{p.get('handle')}",
#                "image": (p.get("image") or {}).get("src"),
#                "price": price_f if price_f else None,
#                "compare_at": compare_f if compare_f else None,
#                "discount_pct": None,
#                "created_at": p.get("created_at") or "",
#                "score": 1,
#            }
#            scored.append(result)

    # sorteer: eerst hoogste score, dan nieuwste
#    scored.sort(key=lambda x: (x.get("score", 0), x.get("created_at", "")), reverse=True)

    # neem top 5
#    top = scored[:5]
#    for item in top:
#        item.pop("score", None)

#    return {
#        "tool": "shopify_search",
#        "query": query,
#        "results": top,
#    }