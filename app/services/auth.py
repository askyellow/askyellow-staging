from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

# ===== IMAGE GENERATION AUTH CHECK =====

def require_auth_session(request: Request):
    # 👇 PRE-FLIGHT ALTIJD TOESTAAN
    if request.method == "OPTIONS":
        return

    session_id = request.headers.get("X-Session-Id") or ""
    if not session_id:
        raise HTTPException(
            status_code=403,
            detail="Login vereist voor image generation"
        )

    conn = get_db_conn()
    user = get_auth_user_from_session(conn, session_id)
    conn.close()

    if not user:
        raise HTTPException(
            status_code=403,
            detail="Ongeldige of verlopen sessie"
        )
