def detect_specificity(question: str) -> str:
    """
    Bepaalt of een productvraag te breed is of al specifiek.
    Returns: "low" of "high"
    """

    q = question.lower()

    # Signalen dat iets al concreet is
    specificity_keywords = [
        "onder",
        "euro",
        "budget",
        "merk",
        "robot",
        "steel",
        "draadloos",
        "met",
        "voor",
    ]

    if any(k in q for k in specificity_keywords):
        return "high"

    # Standaard: te breed
    return "low"
