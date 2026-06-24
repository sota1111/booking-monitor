import logging

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from booking_monitor.config import validate_config
from booking_monitor.services.config_loader import load_active_config, sample_mode_enabled
from booking_monitor.services.history_factory import get_history
from booking_monitor.services.view_models import (
    build_calendar_view,
    build_safe_config,
    build_status_view,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["views"])
templates = Jinja2Templates(directory="templates")


def require_login(request: Request):
    if not request.session.get("user"):
        return RedirectResponse(url=request.url_for("login_page"), status_code=303)
    return True


@router.get("/dashboard", name="status_page")
async def status_page(request: Request):
    # The dashboard now lives inside the notification-history page (SOT-1199);
    # keep the old /dashboard URL working by redirecting there.
    return RedirectResponse(
        url=request.url_for("notification_history_page"), status_code=307
    )


@router.get("/", name="calendar_page")
async def calendar_page(request: Request):
    auth_check = require_login(request)
    if isinstance(auth_check, RedirectResponse):
        return auth_check

    try:
        config = load_active_config()
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return templates.TemplateResponse(
            request=request,
            name="calendar.html",
            context={"error": str(e), "overview": None, "summary": {}, "targets": []},
        )

    history = get_history()
    calendar = build_calendar_view(config, history)

    return templates.TemplateResponse(
        request=request,
        name="calendar.html",
        context={
            "overview": calendar["overview"],
            "summary": calendar["summary"],
            "targets": calendar["targets"],
            "error": None,
        },
    )


@router.get("/calendar")
async def calendar_redirect(request: Request):
    # The calendar is now the TOP page (SOT-1198); keep the old URL working.
    return RedirectResponse(url=request.url_for("calendar_page"), status_code=307)


@router.get("/history", name="history_page")
async def history_page(request: Request):
    auth_check = require_login(request)
    if isinstance(auth_check, RedirectResponse):
        return auth_check

    history = get_history()
    records = history.get_check_history(limit=200)
    return templates.TemplateResponse(
        request=request, name="history.html", context={"records": records}
    )


@router.get("/notification-history", name="notification_history_page")
async def notification_history_page(request: Request):
    auth_check = require_login(request)
    if isinstance(auth_check, RedirectResponse):
        return auth_check

    history = get_history()
    records = history.get_notification_history(limit=200)

    # The dashboard (summary / target list / manual run) now lives on this page
    # in addition to the notification history table (SOT-1199).
    try:
        config = load_active_config()
        config_warnings = validate_config(config)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return templates.TemplateResponse(
            request=request,
            name="notification_history.html",
            context={
                "records": records,
                "error": str(e),
                "targets": [],
                "summary": {},
                "config_warnings": [],
                "sample_mode": sample_mode_enabled(),
            },
        )

    targets_data, summary = build_status_view(config, history)

    return templates.TemplateResponse(
        request=request,
        name="notification_history.html",
        context={
            "records": records,
            "error": None,
            "targets": targets_data,
            "summary": summary,
            "config_warnings": config_warnings,
            "sample_mode": sample_mode_enabled(),
        },
    )


@router.get("/config", name="config_page")
async def config_page(request: Request):
    auth_check = require_login(request)
    if isinstance(auth_check, RedirectResponse):
        return auth_check

    try:
        config = load_active_config()
        config_warnings = validate_config(config)
    except Exception as e:
        return templates.TemplateResponse(
            request=request,
            name="config.html",
            context={"config": None, "config_warnings": [], "error": str(e)},
        )

    safe_config = build_safe_config(config)
    return templates.TemplateResponse(
        request=request,
        name="config.html",
        context={
            "config": safe_config,
            "config_warnings": config_warnings,
            "error": None,
        },
    )
