from typing import Any, Dict, List, Optional, Tuple

from booking_monitor.history import History
from booking_monitor.notifier import is_snoozed
from booking_monitor.slots import build_calendar_overview, build_slot_grid


def _conditions_dict(conditions: Any) -> Optional[Dict[str, Any]]:
    """Serialize a Conditions object (incl. range fields) for templates/config."""
    if not conditions:
        return None
    data: Dict[str, Any] = {
        "adults": conditions.adults,
        "children_under_3": conditions.children_under_3,
        "days_of_week": conditions.days_of_week,
        "time": conditions.time,
    }
    if getattr(conditions, "date_range", None):
        data["date_range"] = {
            "start": conditions.date_range.start,
            "end": conditions.date_range.end,
        }
    if getattr(conditions, "time_range", None):
        data["time_range"] = {
            "start": conditions.time_range.start,
            "end": conditions.time_range.end,
            "step_minutes": conditions.time_range.step_minutes,
        }
    return data


def build_status_view(config: Any, history: History) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Builds the targets data and summary for the status page."""
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

        conditions = _conditions_dict(target.conditions)
        grid = build_slot_grid(state.get("slots") or [])

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
            "grid": grid,
        })

    # Dashboard summary
    total = len(targets_data)
    active = sum(1 for t in targets_data if t["notify"])
    available_count = sum(1 for t in targets_data if t["status"] == "available")
    full_count = sum(1 for t in targets_data if t["status"] == "unavailable")
    failed_count = sum(1 for t in targets_data if t["status"] == "error")
    unchecked_count = sum(1 for t in targets_data if t["status"] == "unchecked")

    # Aggregate per-slot availability across range-based targets (SOT-1152) so the
    # dashboard can surface how many concrete slots are open vs. monitored.
    available_slots = sum(
        t["grid"]["available_count"] for t in targets_data if t.get("grid")
    )
    total_slots = sum(t["grid"]["total"] for t in targets_data if t.get("grid"))

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
        "available_slots": available_slots,
        "total_slots": total_slots,
        "last_check_at": last_check_at,
        "last_notify_at": last_notify_at,
    }

    return targets_data, summary


def build_calendar_view(config: Any, history: History) -> Dict[str, Any]:
    """Build the availability calendar overview (day×time across all targets).

    Reuses :func:`build_status_view` to obtain per-target slot grids, then aggregates
    them via :func:`build_calendar_overview`. Returns ``{overview, summary}`` where
    ``overview`` is ``None`` when no target uses range-based monitoring (empty state).
    ``targets`` carries the per-target slot grids so the calendar page can render the
    per-target 空き状況グリッド（日付 × 時刻）below the aggregated overview (SOT-1198).
    """
    targets_data, summary = build_status_view(config, history)
    overview = build_calendar_overview(targets_data)
    return {"overview": overview, "summary": summary, "targets": targets_data}


def build_safe_config(config: Any) -> Dict[str, Any]:
    """Builds a safe configuration dictionary (excluding secrets)."""
    targets_data = []
    for target in config.targets:
        conditions = _conditions_dict(target.conditions)
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

    notification = config.notification
    channels = [
        {
            "type": ch.type,
            "webhook_url_env": ch.webhook_url_env,
            "enabled": ch.enabled,
        }
        for ch in getattr(notification, "channels", []) or []
    ]

    return {
        "targets": targets_data,
        "notification": {
            "type": notification.type,
            "webhook_url_env": notification.webhook_url_env,
            "channels": channels,
            "snooze_until": getattr(notification, "snooze_until", None),
            "snoozed": is_snoozed(getattr(notification, "snooze_until", None)),
        },
    }
