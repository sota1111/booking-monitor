import os
from functools import wraps
from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

auth_bp = Blueprint("auth", __name__)

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("auth.login_page"))
        return f(*args, **kwargs)
    return decorated

@auth_bp.route("/login", methods=["GET"])
def login_page():
    return render_template(
        "login.html",
        firebase_api_key=os.environ.get("FIREBASE_API_KEY", ""),
        firebase_auth_domain=os.environ.get("FIREBASE_AUTH_DOMAIN", ""),
        firebase_project_id=os.environ.get("FIREBASE_PROJECT_ID", ""),
        firebase_app_id=os.environ.get("FIREBASE_APP_ID", ""),
    )

@auth_bp.route("/session", methods=["POST"])
def create_session():
    import firebase_admin  # type: ignore
    from firebase_admin import auth as firebase_auth  # type: ignore

    if not firebase_admin._apps:
        firebase_admin.initialize_app()

    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    id_token = data.get("idToken", "")
    allowed_emails_str = os.environ.get("ALLOWED_USER_EMAILS", "")
    allowed_emails = [e.strip() for e in allowed_emails_str.split(",") if e.strip()]

    try:
        decoded = firebase_auth.verify_id_token(id_token)
        email = decoded.get("email", "")
    except Exception:
        return jsonify({"error": "Invalid token"}), 401

    if allowed_emails and email not in allowed_emails:
        return jsonify({"error": "Email not allowed"}), 403

    session["user"] = email
    return jsonify({"success": True, "email": email})

@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login_page"))
