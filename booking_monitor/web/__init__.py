import logging
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware


def create_app() -> FastAPI:
    """App factory to create and configure the FastAPI application."""
    # Configure logging
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    app = FastAPI(title="Booking Monitor")

    # Session Middleware
    app.add_middleware(
        SessionMiddleware,
        secret_key=os.environ.get("AUTH_SECRET", "change-this-secret"),
        https_only=True,  # Secure cookie (served over HTTPS on Cloud Run)
        same_site="lax",  # HttpOnly is the default
    )

    # Static files if directory exists
    static_dir = os.path.join(os.path.dirname(__file__), "../../static")
    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # Startup auth-config check: log each missing auth setting distinctly so that
    # misconfiguration is visible in Cloud Run logs at boot time.
    @app.on_event("startup")
    def _check_auth_config() -> None:
        firebase_api_key = os.getenv("FIREBASE_WEB_API_KEY") or os.getenv("FIREBASE_API_KEY")
        auth_secret = os.getenv("AUTH_SECRET")
        allowed_emails = os.getenv("ALLOWED_USER_EMAILS")
        missing = False
        if not firebase_api_key:
            logging.warning("FIREBASE_WEB_API_KEY / FIREBASE_API_KEY not configured")
            missing = True
        if not auth_secret:
            logging.warning("AUTH_SECRET not configured")
            missing = True
        if not allowed_emails:
            logging.warning("ALLOWED_USER_EMAILS not configured")
            missing = True
        if not missing:
            logging.info("auth config OK")

    # Sample-data mode (SOT-1152): when enabled, populate the sample config and
    # history files at startup so the dashboard can be evaluated without live
    # scraping. Completely inert when SEED_SAMPLE_DATA is unset (production).
    @app.on_event("startup")
    def _seed_sample_data() -> None:
        from booking_monitor.services.config_loader import sample_mode_enabled

        if not sample_mode_enabled():
            return
        try:
            from booking_monitor.sample_data import seed_all

            config_path = os.getenv("CONFIG_PATH", "config.sample.json")
            seed_all(config_path=config_path)
        except Exception as e:  # pragma: no cover - defensive
            logging.warning("Sample data seeding failed: %s", e)

    # Include routers
    # SOT-1300: the Web is display-only + Firestore registration. The research
    # execution route (POST /run) has been removed; research runs locally.
    from booking_monitor.web.auth import router as auth_router
    from booking_monitor.web.views import router as views_router

    app.include_router(auth_router)
    app.include_router(views_router)

    return app
