import logging
from flask import Blueprint, render_template
from booking_monitor.config import validate_config
from booking_monitor.web.auth import login_required
from booking_monitor.services.config_loader import load_active_config
from booking_monitor.services.history_factory import get_history
from booking_monitor.services.view_models import build_status_view, build_safe_config

logger = logging.getLogger(__name__)
views_bp = Blueprint("views", __name__)

@views_bp.route("/", methods=["GET"])
@login_required
def status_page():
    try:
        config = load_active_config()
        config_warnings = validate_config(config)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return render_template("status.html", error=str(e), targets=[], summary={}, config_warnings=[])

    history = get_history()
    targets_data, summary = build_status_view(config, history)

    return render_template("status.html", targets=targets_data, summary=summary, config_warnings=config_warnings)

@views_bp.route("/history", methods=["GET"])
@login_required
def history_page():
    history = get_history()
    records = history.get_check_history(limit=200)
    return render_template("history.html", records=records)

@views_bp.route("/notification-history", methods=["GET"])
@login_required
def notification_history_page():
    history = get_history()
    records = history.get_notification_history(limit=200)
    return render_template("notification_history.html", records=records)

@views_bp.route("/config", methods=["GET"])
@login_required
def config_page():
    try:
        config = load_active_config()
        config_warnings = validate_config(config)
    except Exception as e:
        return render_template("config.html", config=None, config_warnings=[], error=str(e))

    safe_config = build_safe_config(config)
    return render_template("config.html", config=safe_config, config_warnings=config_warnings, error=None)
