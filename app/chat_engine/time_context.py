from datetime import datetime
import pytz

def build_time_context() -> str:
    tz = pytz.timezone("Europe/Amsterdam")
    now = datetime.now(tz)

    hour = now.hour
    if hour < 6:
        part = "nacht"
    elif hour < 12:
        part = "ochtend"
    elif hour < 18:
        part = "middag"
    else:
        part = "avond"

    return (
        f"Huidige datum: {now.strftime('%A %d %B %Y')}. "
        f"Huidige tijd: {now.strftime('%H:%M')}. "
        f"Dagdeel: {part}."
    )
