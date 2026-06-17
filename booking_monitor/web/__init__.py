import os
import logging
from flask import Flask

def create_app() -> Flask:
    """App factory to create and configure the Flask application."""
    # Configure logging
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    app = Flask(__name__, template_folder="../../templates", static_folder="../../static")
    app.secret_key = os.environ.get("AUTH_SECRET", "change-this-secret")

    # Register Blueprints
    from booking_monitor.web.auth import auth_bp
    from booking_monitor.web.views import views_bp
    from booking_monitor.web.monitor import monitor_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(views_bp)
    app.register_blueprint(monitor_bp)

    return app
