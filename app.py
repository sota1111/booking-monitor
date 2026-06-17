import os
import logging
from functools import wraps
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from booking_monitor.config import load_config, validate_config
from booking_monitor.checker import check_target
from booking_monitor.history import History
from booking_monitor.notifier import Notifier

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("AUTH_SECRET", "change-this-secret")

# Global flag to ensure OIDC_AUDIENCE warning is logged only once
_oidc_audience_warning_logged = False


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated


@app.route("/", methods=["GET"])
@login_required
def status_page():
    try:
        config_path = os.getenv("CONFIG_PATH", "config.json")
        if not os.path.exists(config_path) and os.path.exists("config.example.json"):
            config_path = "config.example.json"
        config = load_config(config_path)
        config_warnings = validate_config(config)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return render_template("status.html", error=str(e), targets=[], summary={}, config_warnings=[])

    history = get_history()
    latest_states = {s["target_name"]: s for s in history.get_all_latest_states()}

    targets_data = []
    for target in config.targets:
        state = latest_states.get(target.name, {})
        available = state.get("available")
        notified = state.get("notified", False)
        checked_at = state.get("checked_at")
        error = state.get("error")

        if error:
            status = "error"
        elif available is None:
            status = "unchecked"
        elif available:
            status = "available"
        else:
            status = "unavailable"

        conditions = None
        if target.conditions:
            conditions = {
                "adults": target.conditions.adults,
                "children_under_3": target.conditions.children_under_3,
                "days_of_week": target.conditions.days_of_week,
                "time": target.conditions.time,
            }

        targets_data.append({
            "name": target.name,
            "site_type": target.site_type,
            "url": target.url,
            "notify": target.notify,
            "interval_seconds": target.interval_seconds,
            "available_keywords": target.available_keywords,
            "unavailable_keywords": target.unavailable_keywords,
            "conditions": conditions,
            "status": status,
            "notified": notified,
            "checked_at": checked_at,
            "error": error,
        })

    # Dashboard summary
    total = len(targets_data)
    active = sum(1 for t in targets_data if t["notify"])
    available_count = sum(1 for t in targets_data if t["status"] == "available")
    full_count = sum(1 for t in targets_data if t["status"] == "unavailable")
    failed_count = sum(1 for t in targets_data if t["status"] == "error")
    unchecked_count = sum(1 for t in targets_data if t["status"] == "unchecked")

    checked_ats = [t["checked_at"] for t in targets_data if t["checked_at"]]
    last_check_at = max(checked_ats) if checked_ats else None

    # Last notification time from notification history
    try:
        notif_history = history.get_notification_history(limit=1)
        last_notify_at = notif_history[0]["sent_at"] if notif_history else None
    except Exception:
        last_notify_at = None

    summary = {
        "total": total,
        "active": active,
        "available": available_count,
        "full": full_count,
        "failed": failed_count,
        "unchecked": unchecked_count,
        "last_check_at": last_check_at,
        "last_notify_at": last_notify_at,
    }

    return render_template("status.html", targets=targets_data, summary=summary, config_warnings=config_warnings)


@app.route("/login", methods=["GET"])
def login_page():
    return render_template(
        "login.html",
        firebase_api_key=os.environ.get("FIREBASE_API_KEY", ""),
        firebase_auth_domain=os.environ.get("FIREBASE_AUTH_DOMAIN", ""),
        firebase_project_id=os.environ.get("FIREBASE_PROJECT_ID", ""),
        firebase_app_id=os.environ.get("FIREBASE_APP_ID", ""),
    )


@app.route("/session", methods=["POST"])
def create_session():
    import firebase_admin
    from firebase_admin import auth as firebase_auth

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


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login_page"))


def get_history():
    """Returns FirestoreHistory if configured, else local History."""
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    if project:
        try:
            from booking_monitor.firestore_history import FirestoreHistory
            return FirestoreHistory()
        except Exception as e:
            logger.warning(f"Firestore unavailable, falling back to local history: {e}")
    return History()


@app.route("/run", methods=["POST"])
def run_monitor():
    # Cloud Scheduler からの OIDC トークン検証
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split("Bearer ")[1]
        try:
            import google.auth.transport.requests
            import google.oauth2.id_token
            request_adapter = google.auth.transport.requests.Request()

            oidc_audience = os.getenv("OIDC_AUDIENCE")
            if not oidc_audience:
                global _oidc_audience_warning_logged
                if not _oidc_audience_warning_logged:
                    logger.warning("OIDC_AUDIENCE is not set. Audience verification is skipped (not recommended).")
                    _oidc_audience_warning_logged = True

            # OIDC トークンを検証 (Audience を指定)
            claims = google.oauth2.id_token.verify_oauth2_token(
                token, request_adapter, audience=oidc_audience
            )

            # 呼び出し元サービスアカウント email の検証 (設定されている場合のみ)
            scheduler_sa_email = os.getenv("SCHEDULER_SA_EMAIL")
            if scheduler_sa_email:
                if claims.get("email") != scheduler_sa_email or not claims.get("email_verified"):
                    logger.warning(f"Unauthorized service account: {claims.get('email')}")
                    return jsonify({"error": "Unauthorized"}), 401
        except Exception as e:
            logger.warning("OIDC token verification failed: %s", type(e).__name__)
            return jsonify({"error": "Unauthorized"}), 401
    elif os.getenv("RUN_API_KEY") and request.headers.get("X-API-KEY") == os.getenv("RUN_API_KEY"):
        # APIキーによる簡易認証（開発・テスト用）
        pass
    else:
        # 認証経路に該当しない場合はデフォルト拒否
        return jsonify({"error": "Unauthorized"}), 401

    try:
        config_path = os.getenv("CONFIG_PATH", "config.json")
        if not os.path.exists(config_path):
            # Fallback to example if config.json doesn't exist for easier testing/dev
            if os.path.exists("config.example.json"):
                config_path = "config.example.json"

        config = load_config(config_path)
        history = get_history()
        notifier = Notifier(config.notification)

        results = []
        for target in config.targets:
            try:
                available, summary = check_target(target)
                last_state = history.get_last_state(target.name)

                was_available = last_state.get("available", False) if last_state else False
                was_notified = last_state.get("notified", False) if last_state else False

                state_changed = available and not was_available
                notified_this_turn = False

                is_notified = was_notified
                if available:
                    if state_changed:
                        if target.notify:
                            try:
                                notifier.send(target, summary)
                                is_notified = True
                                notified_this_turn = True
                                history.store_notification_history(
                                    target_name=target.name,
                                    url=target.url,
                                    summary=summary,
                                    success=True,
                                    skipped=False,
                                )
                            except Exception as notif_err:
                                logger.error(f"Notification failed for {target.name}: {notif_err}")
                                history.store_notification_history(
                                    target_name=target.name,
                                    url=target.url,
                                    summary=summary,
                                    success=False,
                                    skipped=False,
                                    error=str(notif_err),
                                )
                        else:
                            # notify=False: availability found but notification skipped
                            history.store_notification_history(
                                target_name=target.name,
                                url=target.url,
                                summary=summary,
                                success=False,
                                skipped=True,
                            )
                else:
                    is_notified = False

                history.record(target.name, target.url, available, is_notified)
                history.store_check_history(
                    target_name=target.name,
                    url=target.url,
                    available=available,
                    summary=summary,
                    notified=notified_this_turn,
                    state_changed=state_changed,
                )

                results.append({
                    "target": target.name,
                    "available": available,
                    "summary": summary,
                    "notified": notified_this_turn or (available and was_notified),
                    "state_changed": state_changed
                })
            except Exception as e:
                logger.error(f"Error checking target {target.name}: {e}")
                history.record(target.name, target.url, False, False, error=str(e))
                history.store_check_history(
                    target_name=target.name,
                    url=target.url,
                    available=False,
                    summary="",
                    notified=False,
                    state_changed=False,
                    error=str(e),
                )
                results.append({
                    "target": target.name,
                    "available": False,
                    "summary": f"Error: {str(e)}",
                    "notified": False,
                    "state_changed": False
                })

        return jsonify({"status": "ok", "results": results}), 200

    except Exception as e:
        logger.error(f"Execution error: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/history", methods=["GET"])
@login_required
def history_page():
    history = get_history()
    records = history.get_check_history(limit=200)
    return render_template("history.html", records=records)


@app.route("/notification-history", methods=["GET"])
@login_required
def notification_history_page():
    history = get_history()
    records = history.get_notification_history(limit=200)
    return render_template("notification_history.html", records=records)


@app.route("/config", methods=["GET"])
@login_required
def config_page():
    try:
        config_path = os.getenv("CONFIG_PATH", "config.json")
        if not os.path.exists(config_path) and os.path.exists("config.example.json"):
            config_path = "config.example.json"
        config = load_config(config_path)
        config_warnings = validate_config(config)
    except Exception as e:
        return render_template("config.html", config=None, config_warnings=[], error=str(e))

    # Build safe config dict (exclude webhook URLs and secrets)
    targets_data = []
    for target in config.targets:
        conditions = None
        if target.conditions:
            conditions = {
                "adults": target.conditions.adults,
                "children_under_3": target.conditions.children_under_3,
                "days_of_week": target.conditions.days_of_week,
                "time": target.conditions.time,
            }
        targets_data.append({
            "name": target.name,
            "site_type": target.site_type,
            "url": target.url,
            "interval_seconds": target.interval_seconds,
            "available_keywords": target.available_keywords,
            "unavailable_keywords": target.unavailable_keywords,
            "notify": target.notify,
            "conditions": conditions,
        })

    safe_config = {
        "targets": targets_data,
        "notification": {
            "type": config.notification.type,
            # webhook_url_env shows env var name only, not the value
            "webhook_url_env": config.notification.webhook_url_env,
        },
    }

    return render_template("config.html", config=safe_config, config_warnings=config_warnings, error=None)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
