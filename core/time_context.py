from datetime import datetime, timezone

def build_time_context() -> str:
    now = datetime.now(timezone.utc)
    return (
        f"Huidige datum: {now.strftime('%d %B %Y')}. "
        f"De meest recente jaarwisseling vond plaats op "
        f"31 december {now.year - 1}. "
        "Relatieve termen zoals 'afgelopen jaarwisseling', "
        "'recent' en 'vorig jaar' verwijzen naar deze context."
    )
