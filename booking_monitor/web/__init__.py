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

    # Include routers
    from booking_monitor.web.auth import router as auth_router
    from booking_monitor.web.monitor import router as monitor_router
    from booking_monitor.web.views import router as views_router

    app.include_router(auth_router)
    app.include_router(views_router)
    app.include_router(monitor_router)

    return app
