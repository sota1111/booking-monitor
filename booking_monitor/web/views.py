import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from booking_monitor.config import (
    Conditions,
    Target,
    save_config,
    validate_config,
)
from booking_monitor.services.config_loader import (
    load_active_config,
    resolve_writable_config_path,
    sample_mode_enabled,
)
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
    # 監視履歴 is now a tab on the notification-history page (SOT-1186);
    # keep the old /history URL working by redirecting there.
    return RedirectResponse(
        url=request.url_for("notification_history_page"), status_code=307
    )


@router.get("/notification-history", name="notification_history_page")
async def notification_history_page(request: Request):
    auth_check = require_login(request)
    if isinstance(auth_check, RedirectResponse):
        return auth_check

    history = get_history()
    records = history.get_notification_history(limit=200)
    # 監視履歴 (check history) is shown as a second tab on this page (SOT-1186).
    check_records = history.get_check_history(limit=200)

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
                "check_records": check_records,
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
            "check_records": check_records,
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


def _parse_keywords(raw) -> list[str]:
    """Split a comma-separated keyword string (or list) into a clean list."""
    if isinstance(raw, list):
        return [str(kw).strip() for kw in raw if str(kw).strip()]
    return [kw.strip() for kw in str(raw or "").split(",") if kw.strip()]


def _int_field(raw, default: int) -> int:
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError, AttributeError):
        return default


def _bool_field(raw) -> bool:
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"on", "true", "1", "yes"}


@router.post("/targets", name="add_target")
async def add_target(request: Request):
    """Append a new monitoring target from the dashboard form and persist it.

    The dashboard form submits JSON via fetch (matching /run and login), so this
    route reads a JSON body rather than relying on multipart form parsing.
    """
    auth_check = require_login(request)
    if isinstance(auth_check, RedirectResponse):
        return JSONResponse({"status": "error", "error": "Unauthorized"}, status_code=401)

    try:
        data = await request.json()
    except Exception:
        data = {}

    name = str(data.get("name", "")).strip()
    url = str(data.get("url", "")).strip()

    # Name and URL are required.
    if not name or not url:
        return JSONResponse(
            {"status": "error", "error": "店舗名とURLは必須です"}, status_code=400
        )

    days = data.get("days_of_week") or []
    if not isinstance(days, list):
        days = [days]

    conditions = Conditions(
        adults=_int_field(data.get("adults"), 2),
        children_under_3=_int_field(data.get("children_under_3"), 0),
        days_of_week=[str(d) for d in days],
        time=str(data.get("time", "")).strip(),
    )

    target = Target(
        name=name,
        url=url,
        interval_seconds=_int_field(data.get("interval_seconds"), 300),
        available_keywords=_parse_keywords(data.get("available_keywords", "")),
        unavailable_keywords=_parse_keywords(data.get("unavailable_keywords", "")),
        notify=_bool_field(data.get("notify", False)),
        site_type=str(data.get("site_type", "generic")).strip() or "generic",
        conditions=conditions,
    )

    try:
        config = load_active_config()
        config.targets.append(target)
        save_config(config, resolve_writable_config_path())
    except Exception as e:
        logger.error(f"Failed to add target: {e}")
        return JSONResponse(
            {"status": "error", "error": "保存に失敗しました"}, status_code=500
        )

    return JSONResponse({"status": "ok", "name": name})
