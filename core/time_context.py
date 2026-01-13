from datetime import datetime, timezone

class TimeContext:
    def __init__(self):
        self.now = datetime.now(timezone.utc)

    def system_prompt(self) -> str:
        return (
            f"Huidige datum: {self.now.strftime('%d %B %Y')}. "
            f"De meest recente jaarwisseling vond plaats op "
            f"31 december {self.now.year - 1}. "
            "Relatieve termen zoals 'afgelopen jaarwisseling', "
            "'recent' en 'vorig jaar' verwijzen naar deze context."
        )

    def today_string(self):
        return self.now.strftime("%A %d %B %Y")

    def time_string(self):
        return self.now.strftime("%H:%M")

