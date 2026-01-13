# core/time.py

from datetime import datetime, timezone


class TimeContext:
    """
    Centrale tijd-logica voor AskYellow.
    De AI mag hier NIET van afwijken.
    """

    def __init__(self):
        self.now = datetime.now(timezone.utc)

    @property
    def current_date(self) -> str:
        return self.now.strftime("%d %B %Y")

    @property
    def current_year(self) -> int:
        return self.now.year

    @property
    def latest_year_change(self) -> str:
        return f"31 december {self.current_year - 1}"

    def system_prompt(self) -> str:
        return (
            f"Huidige datum: {self.current_date}. "
            f"De meest recente jaarwisseling vond plaats op "
            f"{self.latest_year_change}. "
            "Relatieve tijdsaanduidingen zoals "
            "'afgelopen jaarwisseling', 'recent', "
            "'vorig jaar' en 'dit jaar' moeten "
            "altijd volgens deze context worden geïnterpreteerd. "
            "Gebruik geen eigen aannames over tijd."
        )
