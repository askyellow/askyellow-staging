def get_search_questions(category: str) -> list[str]:
    """
    Geeft voorbeeldvragen voor een categorie.
    Nog geen AI, gewoon netjes voorbereid.
    """

    QUESTIONS = {
        "huishouden": [
            "Wat voor type zoek je (bijvoorbeeld een robot-, steel- of gewone stofzuiger)?",
            "Heb je een budget in gedachten?"
        ],
        "beeld_en_geluid": [
            "Waar ga je het vooral voor gebruiken (muziek, films, gamen)?",
            "Heb je een voorkeur voor een bepaald type of formaat?"
        ],
        "gaming": [
            "Voor welk platform zoek je iets (PC, PlayStation, Xbox)?",
            "Wat is ongeveer je budget?"
        ],
    }

    return QUESTIONS.get(category, [])
