import os
import psycopg2
import psycopg2.extras

# =============================================================
# POSTGRES DB FOR USERS / CONVERSATIONS / MESSAGES
# =============================================================

# DATABASE_URL komt uit de Render-omgeving
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is niet ingesteld (env var DATABASE_URL).")

def get_db_conn():
    """Open een nieuwe PostgreSQL-verbinding met dict-rows."""
    conn = psycopg2.connect(
        DATABASE_URL,
        cursor_factory=psycopg2.extras.RealDictCursor
    )
    return conn

def get_db():
    """FastAPI dependency die de verbinding automatisch weer sluit."""
    conn = get_db_conn()
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """Maak basis-tabellen aan als ze nog niet bestaan."""
    conn = get_db_conn()
    cur = conn.cursor()

    # Users: 1 rij per (anon/persoonlijke) sessie
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            session_id TEXT UNIQUE NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )

    # Conversations: 1 of meer gesprekken per user
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_message_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            title TEXT
        );
        """
    )

    # Messages: alle losse berichten
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )

    # Auth users: aparte tabel voor geregistreerde accounts
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_users (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_login TIMESTAMPTZ
        );
        """
    )

    # User sessions voor ingelogde gebruikers
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_sessions (
            session_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
            expires_at TIMESTAMPTZ NOT NULL
        );
        """
    )

    conn.commit()
    conn.close()