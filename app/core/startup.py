# core/startup.py

from ..db.models import init_db

def on_startup():
    # Zorg dat DB-tabellen bestaan
    init_db()
