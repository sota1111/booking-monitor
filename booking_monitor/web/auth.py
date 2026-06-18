import logging
import os
import secrets

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["auth"])
templates = Jinja2Templates(directory="templates")

# Server-side Firebase REST authentication (案1).
# The browser never talks to Firebase directly; the server verifies the
# email/password via the Identity Toolkit REST API using a server-side Web API key.
IDENTITY_TOOLKIT_SIGN_IN_URL = (
    "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
)
CSRF_COOKIE_NAME = "csrf_token"
GENERIC_AUTH_ERROR = "メールアドレスまたはパスワードが正しくありません"

def require_login(request: Request):
    if not request.session.get("user"):
        return None  # Will be handled in the endpoint or by returning a RedirectResponse
    return request.session.get("user")

async def login_required(request: Request):
    if not request.session.get("user"):
        raise HTTPException(status_code=303, detail="Redirecting to login")

# For template use
def get_user(request: Request):
    return request.session.get("user")

@router.get("/login", name="login_page")
async def login_page(request: Request):
    # Double-submit CSRF token: rendered into the form and mirrored as a cookie.
    csrf_token = secrets.token_urlsafe(32)
    response = templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"csrf_token": csrf_token},
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        csrf_token,
        max_age=3600,
        secure=True,
        httponly=False,  # readable by the login form JS for the double-submit check
        samesite="lax",
    )
    return response

@router.post("/session", name="create_session")
async def create_session(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "No JSON body"}, status_code=400)

    email = (data.get("email") or "").strip()
    password = data.get("password") or ""
    csrf_token = data.get("csrf_token") or ""

    if not email or not password:
        return JSONResponse(
            {"error": "メールアドレスとパスワードを入力してください"}, status_code=400
        )

    # CSRF double-submit validation: body token must equal the cookie token.
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME, "")
    if (
        not csrf_token
        or not cookie_token
        or not secrets.compare_digest(csrf_token, cookie_token)
    ):
        return JSONResponse({"error": "CSRF token mismatch"}, status_code=403)

    api_key = os.environ.get("FIREBASE_WEB_API_KEY") or os.environ.get("FIREBASE_API_KEY") or ""
    if not api_key:
        logger.error("FIREBASE_WEB_API_KEY / FIREBASE_API_KEY is not configured")
        return JSONResponse({"error": "サーバー設定エラー"}, status_code=500)

    # Verify credentials server-side via Identity Toolkit REST.
    # NEVER log the password or the raw credential payload.
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                IDENTITY_TOOLKIT_SIGN_IN_URL,
                params={"key": api_key},
                json={
                    "email": email,
                    "password": password,
                    "returnSecureToken": True,
                },
            )
    except Exception:
        logger.warning("Identity Toolkit request failed for a login attempt")
        return JSONResponse({"error": GENERIC_AUTH_ERROR}, status_code=401)

    if resp.status_code != 200:
        # EMAIL_NOT_FOUND / INVALID_PASSWORD / INVALID_LOGIN_CREDENTIALS, etc.
        logger.info(
            "Login failed (Identity Toolkit returned status %s)", resp.status_code
        )
        return JSONResponse({"error": GENERIC_AUTH_ERROR}, status_code=401)

    body = resp.json()
    verified_email = (body.get("email") or email).strip()

    allowed_emails_str = os.environ.get("ALLOWED_USER_EMAILS", "")
    allowed_emails = [e.strip() for e in allowed_emails_str.split(",") if e.strip()]
    if allowed_emails and verified_email not in allowed_emails:
        return JSONResponse(
            {"error": "このメールアドレスは許可されていません"}, status_code=403
        )

    request.session["user"] = verified_email
    return {"success": True, "email": verified_email}

@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url=request.url_for("login_page"), status_code=303)
