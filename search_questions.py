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
            "Waar ga je het vooral voor gebruiken? (muziek, films, gamen)?",
            "Heb je een voorkeur voor een bepaald type of formaat?"
        ],
        "gaming": [
            "Voor welk platform zoek je iets? (PC, PlayStation, Xbox)?",
            "Wat is ongeveer je budget?"
        ],
        "mode": [
            "Wat zoek je specifiek voor mode? (jas, vest, broek, overhemd, tshirt)?",
            "Wat is ongeveer je budget?"
        ],
        "speelgoed": [
            "Voor welke doelgroep (leeftijd) zoek je speelgoed? (kleine kinderen, wat grotere kinderen, lego, playmobiel)?",
            "Heb je ongeveer een budget?"
        ],
        "sport": [
            "Voor wat voor sport zoek je iets? (voetbal, tennis, zwemmen, boksen)?",
            "Wat is ongeveer je budget?"
        ],
        "beauty_verzorging": [
            "Wat voor verzorgingsproduct zoek je specifiek? (PC, PlayStation, Xbox)?",
            "Wat is ongeveer je budget?"
        ],
        "mode_accessoires": [
            "Voor welk platform zoek je iets (PC, PlayStation, Xbox)?",
            "Wat is ongeveer je budget?"
        ],
    }

    return QUESTIONS.get(category, [])
