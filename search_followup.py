def interpret_search_followup(answer: str) -> str:
    """
    Interpreteert reactie op een verkopersvraag.
    Returns:
    - "accept"  -> dit is voldoende
    - "refine"  -> zoek verder / anders
    - "unknown" -> niet duidelijk
    """

    if not answer:
        return "unknown"

    a = answer.lower()

    accept_keywords = [
        "ja",
        "is goed",
        "prima",
        "genoeg",
        "perfect",
        "laat maar zien",
        "dat is goed"
    ]

    refine_keywords = [
        "nee",
        "verder",
        "anders",
        "goedkoper",
        "duurder",
        "stil",
        "kleiner",
        "groter",
        "met",
        "zonder",
        "liever"
    ]

    if any(k in a for k in accept_keywords):
        return "accept"

    if any(k in a for k in refine_keywords):
        return "refine"

    return "unknown"
