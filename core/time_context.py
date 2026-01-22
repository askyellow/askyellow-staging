from datetime import datetime, timezone
from zoneinfo import ZoneInfo

def build_time_context() -> str:
    now = datetime.now(ZoneInfo("Europe/Amsterdam"))
    return (
        f"Huidige datum: {now.strftime('%d %B %Y')}. "
        f"De meest recente jaarwisseling vond plaats op "
        f"31 december {now.year - 1}. "
        "Relatieve termen zoals 'afgelopen jaarwisseling', "
        "'recent' en 'vorig jaar' verwijzen naar deze context."
    )
def day_part() -> str:
    hour = datetime.now(ZoneInfo("Europe/Amsterdam")).hour
    if hour < 12:
        return "goedemorgen"
    elif hour < 18:
        return "goedemiddag"
    else:
        return "goedenavond"

def greeting() -> str:
    return day_part().capitalize()

def build_llm_time_hint() -> str:
    now = datetime.now(ZoneInfo("Europe/Amsterdam"))
    if now.hour < 12:
        return "Het is ochtend."
    elif now.hour < 18:
        return "Het is middag."
    else:
        return "Het is avond."

def get_logical_date():
    return datetime.now(ZoneInfo("Europe/Amsterdam")).date()
