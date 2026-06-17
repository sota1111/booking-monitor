import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="", tags=["auth"])
templates = Jinja2Templates(directory="templates")

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
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "firebase_api_key": os.environ.get("FIREBASE_API_KEY", ""),
            "firebase_auth_domain": os.environ.get("FIREBASE_AUTH_DOMAIN", ""),
            "firebase_project_id": os.environ.get("FIREBASE_PROJECT_ID", ""),
            "firebase_app_id": os.environ.get("FIREBASE_APP_ID", ""),
        }
    )

@router.post("/session", name="create_session")
async def create_session(request: Request):
    import firebase_admin  # type: ignore
    from firebase_admin import auth as firebase_auth  # type: ignore

    if not firebase_admin._apps:
        firebase_admin.initialize_app()

    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "No JSON body"}, status_code=400)

    id_token = data.get("idToken", "")
    allowed_emails_str = os.environ.get("ALLOWED_USER_EMAILS", "")
    allowed_emails = [e.strip() for e in allowed_emails_str.split(",") if e.strip()]

    try:
        decoded = firebase_auth.verify_id_token(id_token)
        email = decoded.get("email", "")
    except Exception:
        return JSONResponse({"error": "Invalid token"}, status_code=401)

    if allowed_emails and email not in allowed_emails:
        return JSONResponse({"error": "Email not allowed"}, status_code=403)

    request.session["user"] = email
    return {"success": True, "email": email}

@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url=request.url_for("login_page"), status_code=303)
