
from datetime import datetime, timedelta
import pytz

def get_logical_date():
    tz = pytz.timezone("Europe/Amsterdam")
    now = datetime.now(tz)
    if now.hour < 3:
        return (now - timedelta(days=1)).date()
    return now.date()
