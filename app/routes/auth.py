from fastapi import APIRouter, HTTPException
from app.db.connection import get_db_conn
from datetime import datetime, timedelta
from passlib.context import CryptContext

pwd_context = CryptContext(
    schemes=["bcrypt_sha256", "bcrypt", "pbkdf2_sha256"],
    deprecated="auto"
)
def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

import uuid

router = APIRouter()


@router.post("/auth/login")
async def login(payload: dict):
    email = (payload.get("email") or "").lower().strip()
    password = payload.get("password") or ""
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email en wachtwoord verplicht")

    conn = get_db_conn()
    cur = conn.cursor()

    # gebruiker ophalen
    cur.execute(
        "SELECT id, password_hash, first_name FROM auth_users WHERE email = %s",
        (email,)
    )

    user = cur.fetchone()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user_id, password_hash, first_name = user

    if not verify_password(password, password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    session_id = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(days=7)

    cur.execute("""
        INSERT INTO user_sessions (session_id, user_id, expires_at)
        VALUES (%s, %s, %s)
    """, (session_id, user_id, expires_at))


    cur.execute(
        "UPDATE auth_users SET last_login = NOW() WHERE id = %s",
        (user_id,)
    )

    conn.commit()
    conn.close()

    return {
    "success": True,
    "session": session_id,
    "first_name": first_name
}



def get_auth_user_from_session(conn, session_id: str):
    cur = conn.cursor()
    cur.execute("""
        SELECT au.id, au.first_name
        FROM user_sessions us
        JOIN auth_users au ON au.id = us.user_id
        WHERE us.session_id = %s
          AND us.expires_at > NOW()
    """, (session_id,))

    row = cur.fetchone()
    if not row:
        return None

    user_id, first_name = row

    return {
        "id": user_id,
        "first_name": first_name
}


def get_or_create_user_for_auth(conn, auth_user_id: int):
    cur = conn.cursor()
    stable_sid = f"auth-{auth_user_id}"

    cur.execute(
        "SELECT id FROM users WHERE session_id = %s",
        (stable_sid,)
    )
    row = cur.fetchone()
    if row:
        return row[0]

    cur.execute(
        """
        INSERT INTO users (session_id)
        VALUES (%s)
        RETURNING id
        """,
        (stable_sid,)
    )
    user_id = cur.fetchone()[0]
    conn.commit()
    return user_id



    cur.execute(
        """
        INSERT INTO users (session_id)
        VALUES (%s)
        RETURNING id
        """,
        (stable_sid,)
    )
    conn.commit()
    row = cur.fetchone()
    row = cur.fetchone()
    return row[0]


    # 2) Anders maken we 'm aan
    cur.execute(
        """
        INSERT INTO users (session_id)
        VALUES (%s)
        RETURNING id
        """,
        (stable_sid,),
    )
    conn.commit()
    row = cur.fetchone()
    return row["id"] if not isinstance(row, dict) else row["id"]

@router.post("/auth/register")
async def register(payload: dict):
    email = (payload.get("email") or "").lower().strip()
    password = payload.get("password") or ""
    first_name = (payload.get("first_name") or "").strip()
    last_name = (payload.get("last_name") or "").strip()

    if not email or not password or not first_name or not last_name:
        raise HTTPException(status_code=400, detail="Alle velden zijn verplicht")

    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Wachtwoord te kort")

    conn = get_db_conn()
    cur = conn.cursor()

    # bestaat email al?
    cur.execute("SELECT id FROM auth_users WHERE email = %s", (email,))
    if cur.fetchone():
        conn.close()
        raise HTTPException(status_code=409, detail="Email bestaat al")

    safe_password = normalize_password(password)
    password_hash = pwd_context.hash(safe_password)
    pwd_context.verify(password, password_hash)


    # gebruiker aanmaken
    cur.execute(
        """
        INSERT INTO auth_users (email, password_hash, first_name, last_name)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (email, password_hash, first_name, last_name)
    )
    user_id = cur.fetchone()[0]

    # auto-login sessie
    session_id = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(days=7)

    cur.execute(
        """
        INSERT INTO user_sessions (session_id, user_id, expires_at)
        VALUES (%s, %s, %s)
        """,
        (session_id, user_id, expires_at)
    )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "session": session_id,
        "first_name": first_name
    }

@router.post("/auth/request-password-reset")
async def request_password_reset(payload: dict):
    email = (payload.get("email") or "").lower().strip()

    conn = get_db_conn()
    cur = conn.cursor()

    cur.execute(
        "SELECT id FROM auth_users WHERE email = %s",
        (email,)
    )
    user = cur.fetchone()

    if user:
        token = str(uuid.uuid4())
        expires = datetime.utcnow() + timedelta(minutes=30)

    user_id = user[0]

    cur.execute(
        """
        UPDATE auth_users
        SET password_hash = %s,
            reset_token = NULL,
            reset_expires = NULL
        WHERE id = %s
        """,
        (new_hash, user_id)
    )


    conn.commit()

    reset_link = f"https://askyellow.nl/reset.html?token={token}"

    try:
            resend.Emails.send({
    "from": "AskYellow <no-reply@askyellow.nl>",
    "to": email,
    "subject": "Reset je wachtwoord voor AskYellow",
    "html": f"""
        <p>Hoi,</p>

        <p>Via onderstaande link kun je een nieuw wachtwoord instellen:</p>

        <p>
          <a href="{reset_link}">
            Reset je wachtwoord
          </a>
        </p>

        <p>Deze link is <strong>30 minuten geldig</strong>.</p>

        <p>Groet,<br>
        YellowMind</p>
    """
})

    except Exception as e:
            # fallback: log link als mail faalt
            print("❌ MAIL FAILED — RESET LINK:", reset_link)
            print(e)

    conn.close()

    # ⚠️ altijd hetzelfde antwoord (security)
    return {
        "message": "Als dit e-mailadres bestaat, ontvang je een reset-link."
    }

@router.post("/auth/reset-password")
async def reset_password(payload: dict):
    token = payload.get("token")
    new_password = payload.get("password")

    if not token or not new_password:
        raise HTTPException(status_code=400, detail="Token en nieuw wachtwoord verplicht")

    conn = get_db_conn()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id
        FROM auth_users
        WHERE reset_token = %s
          AND reset_expires > NOW()
        """,
        (token,)
    )
    user = cur.fetchone()

    if not user:
        raise HTTPException(status_code=400, detail="Ongeldige of verlopen reset-link")

    # 🔑 HIER gaat het NU goed
    new_hash = pwd_context.hash(new_password)

    cur.execute(
        """
        UPDATE auth_users
        SET password_hash = %s,
            reset_token = NULL,
            reset_expires = NULL
        WHERE id = %s
        """,
        (new_hash, user["id"])
    )

    conn.commit()
    conn.close()

    return {"success": True}