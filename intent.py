def detect_intent(question: str) -> str:
    """
    Bepaalt de INHOUDELIJKE intent van de gebruiker.
    Dit is GEEN technische routing (image/search/etc).

    Mogelijke returns (v1):
    - "product"
    - "info"
    """

    if not question:
        return "info"

    q = question.lower()

    # -----------------------------
    # PRODUCT-INTENT
    # -----------------------------
    product_keywords = [
        "ik zoek",
        "ik wil",
        "kopen",
        "beste",
        "aanrader",
        "stofzuiger",
        "koptelefoon",
        "tv",
        "schoenen",
        "jas",
        "cadeau",
    ]

    if any(k in q for k in product_keywords):
        return "product"

    # -----------------------------
    # DEFAULT
    # -----------------------------
    return "info"
