import json
import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class DateRange:
    """Inclusive date range as ``YYYY-MM-DD`` strings."""

    start: str
    end: str


@dataclass
class TimeRange:
    """Time range as ``HH:MM`` strings with a step in minutes (default 15)."""

    start: str
    end: str
    step_minutes: int = 15


@dataclass
class Conditions:
    adults: int = 2
    children_under_3: int = 0
    days_of_week: List[str] = field(default_factory=list)
    time: str = ""
    # Range-based monitoring (SOT-833). When set, the monitor expands the
    # date_range x time_range product (AND search) into individual slots and
    # reports per-slot availability. Legacy ``time``/``days_of_week`` remain as
    # a fallback when these are absent (backward compatible).
    date_range: Optional[DateRange] = None
    time_range: Optional[TimeRange] = None


@dataclass
class Target:
    name: str
    url: str
    interval_seconds: int
    available_keywords: List[str]
    unavailable_keywords: List[str]
    notify: bool
    site_type: str = "generic"
    conditions: Optional[Conditions] = None
    session_state_env: str = ""


@dataclass
class NotificationChannel:
    """A single notification destination (e.g. a Discord webhook).

    ``webhook_url_env`` names the environment variable holding the secret URL (the
    value itself is never stored in config). ``enabled`` lets the human pause one
    channel without removing it.
    """

    type: str
    webhook_url_env: str = ""
    enabled: bool = True


@dataclass
class Notification:
    type: str
    webhook_url_env: str = ""
    # Multiple notification destinations (SOT-886). When non-empty, notifications are
    # sent to every enabled channel. When empty, the legacy single
    # ``type``/``webhook_url_env`` path is used (backward compatible).
    channels: List[NotificationChannel] = field(default_factory=list)
    # Snooze / pause (SOT-886): ISO 8601 UTC timestamp. While ``now`` is before this
    # time, notifications are suppressed. ``None`` (or a past time) means active.
    snooze_until: Optional[str] = None


@dataclass
class Config:
    targets: List[Target]
    notification: Notification


def target_from_dict(t: dict) -> Target:
    """Deserialize a single target dict (incl. conditions/range fields) into a Target.

    Shared by ``load_config`` (config.json) and the Firestore targets store so both
    backends produce identical Target objects.
    """
    conditions_data = t.get("conditions")
    conditions = None
    if conditions_data:
        date_range = None
        dr = conditions_data.get("date_range")
        if dr and dr.get("start") and dr.get("end"):
            date_range = DateRange(start=dr["start"], end=dr["end"])

        time_range = None
        tr = conditions_data.get("time_range")
        if tr and tr.get("start") and tr.get("end"):
            time_range = TimeRange(
                start=tr["start"],
                end=tr["end"],
                step_minutes=int(tr.get("step_minutes", 15)),
            )

        conditions = Conditions(
            adults=conditions_data.get("adults", 2),
            children_under_3=conditions_data.get("children_under_3", 0),
            days_of_week=conditions_data.get("days_of_week", []),
            time=conditions_data.get("time", ""),
            date_range=date_range,
            time_range=time_range,
        )
    return Target(
        name=t["name"],
        url=t["url"],
        interval_seconds=t.get("interval_seconds", 300),
        available_keywords=t.get("available_keywords", []),
        unavailable_keywords=t.get("unavailable_keywords", []),
        notify=t.get("notify", True),
        site_type=t.get("site_type", "generic"),
        conditions=conditions,
        session_state_env=t.get("session_state_env", ""),
    )


def load_config(path: str) -> Config:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    targets = [target_from_dict(t) for t in data.get("targets", [])]

    notif_data = data.get("notification", {})
    channels = []
    for ch in notif_data.get("channels", []) or []:
        channels.append(
            NotificationChannel(
                type=ch.get("type", "discord"),
                webhook_url_env=ch.get("webhook_url_env", ""),
                enabled=ch.get("enabled", True),
            )
        )
    notification = Notification(
        type=notif_data.get("type", "discord"),
        webhook_url_env=notif_data.get("webhook_url_env", "DISCORD_WEBHOOK_URL"),
        channels=channels,
        snooze_until=notif_data.get("snooze_until"),
    )

    if not targets:
        raise ValueError("No targets defined in config")

    return Config(targets=targets, notification=notification)


def _conditions_to_dict(conditions: Optional[Conditions]) -> Optional[dict]:
    if conditions is None:
        return None
    data: dict = {
        "adults": conditions.adults,
        "children_under_3": conditions.children_under_3,
        "days_of_week": list(conditions.days_of_week),
        "time": conditions.time,
    }
    if conditions.date_range is not None:
        data["date_range"] = {
            "start": conditions.date_range.start,
            "end": conditions.date_range.end,
        }
    if conditions.time_range is not None:
        data["time_range"] = {
            "start": conditions.time_range.start,
            "end": conditions.time_range.end,
            "step_minutes": conditions.time_range.step_minutes,
        }
    return data


def target_to_dict(target: Target) -> dict:
    """Serialize a single Target (incl. conditions/range fields) to a plain dict.

    Shared by ``save_config`` (config.json) and the Firestore targets store.
    """
    data: dict = {
        "name": target.name,
        "url": target.url,
        "interval_seconds": target.interval_seconds,
        "available_keywords": list(target.available_keywords),
        "unavailable_keywords": list(target.unavailable_keywords),
        "notify": target.notify,
        "site_type": target.site_type,
        "session_state_env": target.session_state_env,
    }
    conditions = _conditions_to_dict(target.conditions)
    if conditions is not None:
        data["conditions"] = conditions
    return data


# Backwards-compatible private alias (kept so existing internal references work).
_target_to_dict = target_to_dict


def _notification_to_dict(notification: Notification) -> dict:
    data: dict = {
        "type": notification.type,
        "webhook_url_env": notification.webhook_url_env,
    }
    if notification.channels:
        data["channels"] = [
            {
                "type": ch.type,
                "webhook_url_env": ch.webhook_url_env,
                "enabled": ch.enabled,
            }
            for ch in notification.channels
        ]
    if notification.snooze_until is not None:
        data["snooze_until"] = notification.snooze_until
    return data


def save_config(config: Config, path: str) -> None:
    """Serialize ``config`` back to JSON at ``path`` (round-trips with load_config)."""
    data = {
        "targets": [_target_to_dict(t) for t in config.targets],
        "notification": _notification_to_dict(config.notification),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def validate_config(config: Config) -> list[str]:
    """Validate config and return list of warning messages."""
    warnings = []

    if not config.targets:
        warnings.append("No targets defined in config")

    for i, target in enumerate(config.targets):
        if not target.name:
            warnings.append(f"Target {i}: missing 'name'")
        if not target.url:
            warnings.append(f"Target {i} ({target.name}): missing 'url'")
        if target.interval_seconds < 60:
            warnings.append(
                f"Target '{target.name}': interval_seconds={target.interval_seconds} "
                f"is less than 60 seconds (may be too aggressive)"
            )
        if not target.available_keywords and not target.unavailable_keywords:
            warnings.append(
                f"Target '{target.name}': no available_keywords or unavailable_keywords defined"
            )

    return warnings
