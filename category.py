def detect_category(question: str) -> str | None:
    """
    Bepaalt de hoofdcategorie van de vraag.
    Retourneert een categorie-key of None.
    """

    if not question:
        return None

    q = question.lower()

    CATEGORY_KEYWORDS = {
        "huishouden": [
            "stofzuiger",
            "wasmachine",
            "droger",
            "vaatwasser",
            "strijkijzer",
            "keukenmachine",
            "airfryer",
        ],
        "beeld_en_geluid": [
            "tv",
            "televisie",
            "koptelefoon",
            "speaker",
            "soundbar",
            "oortjes",
        ],
        "gaming": [
            "gaming",
            "game",
            "console",
            "playstation",
            "xbox",
            "pc",
        ],
        "mode": [
            "jas",
            "broek",
            "schoenen",
            "trui",
            "jurk",
        ],
        "mode_accessoires": [
            "tas",
            "horloge",
            "riem",
            "zonnebril",
        ],
        "beauty_verzorging": [
            "verzorging",
            "make-up",
            "crème",
            "trimmer",
            "scheerapparaat",
        ],
        "sport": [
            "fitness",
            "hardlopen",
            "sport",
            "fiets",
            "yoga",
        ],
        "speelgoed": [
            "speelgoed",
            "lego",
            "pop",
            "spel",
        ],
    }

    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(k in q for k in keywords):
            return category

    return None
