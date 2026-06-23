"""Sample (mock) data seeding for dashboard evaluation (SOT-1152).

This module lets the human evaluate the dashboard *without* live scraping by
registering a handful of realistic booking-monitor targets and populating the
three history JSONL files (`history.jsonl`, `check_history.jsonl`,
`notification_history.jsonl`) with deterministic, varied sample records.

Design goals:

- **Opt-in & safe.** Nothing here runs in production unless explicitly enabled
  (env ``SEED_SAMPLE_DATA`` or the CLI ``scripts/seed_sample_data.py``).
- **Idempotent.** Every generated record is tagged ``"sample": true``. Re-seeding
  removes only the previously-written sample lines and regenerates them, while
  preserving any real (non-sample) records already in the files.
- **Pure-ish & deterministic.** Given a fixed "now", the generated data is stable
  (no randomness, no network, no Playwright).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Marker stored on every generated record so re-seeding can find and replace only
# the sample lines without touching real history.
SAMPLE_TAG = "sample"

# History file names (kept in sync with booking_monitor.history defaults).
_HISTORY_FILE = "history.jsonl"
_CHECK_HISTORY_FILE = "check_history.jsonl"
_NOTIFICATION_HISTORY_FILE = "notification_history.jsonl"

_WEEKDAY_INDEX = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _next_weekend_range(now: datetime, weeks: int = 2) -> Dict[str, str]:
    """A ``date_range`` spanning roughly the next ``weeks`` weeks from ``now``."""
    start = now.date() + timedelta(days=1)
    end = start + timedelta(weeks=weeks)
    return {"start": start.isoformat(), "end": end.isoformat()}


# --------------------------------------------------------------------------- #
# Sample config (targets)
# --------------------------------------------------------------------------- #
def build_sample_targets(now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Return 5 realistic, varied sample target dicts (config-file shape)."""
    now = now or _now()
    rng = _next_weekend_range(now, weeks=2)

    return [
        # Range-based tablecheck target (renders a slot grid + calendar).
        {
            "name": "りくろーおじさん リクカフェテラス",
            "url": "https://www.tablecheck.com/shops/rikuro-rikucafeterrace/reserve",
            "interval_seconds": 300,
            "available_keywords": ["空きあり", "予約可能", "○"],
            "unavailable_keywords": ["満席", "空きなし", "予約不可"],
            "notify": True,
            "site_type": "tablecheck",
            "conditions": {
                "adults": 2,
                "children_under_3": 1,
                "days_of_week": ["Saturday", "Sunday"],
                "date_range": rng,
                "time_range": {"start": "11:00", "end": "15:00", "step_minutes": 60},
            },
        },
        # Second range-based target (generic).
        {
            "name": "サンプル・ビストロ 北浜",
            "url": "https://example.com/shops/bistro-kitahama/reserve",
            "interval_seconds": 600,
            "available_keywords": ["予約可能", "空席"],
            "unavailable_keywords": ["満席", "受付終了"],
            "notify": True,
            "site_type": "generic",
            "conditions": {
                "adults": 4,
                "children_under_3": 0,
                "days_of_week": ["Friday", "Saturday"],
                "date_range": rng,
                "time_range": {"start": "18:00", "end": "20:00", "step_minutes": 60},
            },
        },
        # Legacy single-time target (no slot grid).
        {
            "name": "サンプル・寿司 道頓堀",
            "url": "https://example.com/shops/sushi-dotonbori/reserve",
            "interval_seconds": 300,
            "available_keywords": ["空きあり", "予約可能"],
            "unavailable_keywords": ["満席"],
            "notify": True,
            "site_type": "tablecheck",
            "conditions": {
                "adults": 2,
                "children_under_3": 0,
                "days_of_week": ["Saturday"],
                "time": "19:00",
            },
        },
        # Notify-off target (monitored but muted).
        {
            "name": "サンプル・カフェ 中之島",
            "url": "https://example.com/shops/cafe-nakanoshima/reserve",
            "interval_seconds": 900,
            "available_keywords": ["空きあり"],
            "unavailable_keywords": ["満席"],
            "notify": False,
            "site_type": "generic",
            "conditions": {
                "adults": 3,
                "children_under_3": 2,
                "days_of_week": ["Sunday"],
                "time": "12:00",
            },
        },
        # Target intended to surface an error state on the dashboard.
        {
            "name": "サンプル・焼肉 天王寺",
            "url": "https://example.com/shops/yakiniku-tennoji/reserve",
            "interval_seconds": 300,
            "available_keywords": ["空きあり"],
            "unavailable_keywords": ["満席"],
            "notify": True,
            "site_type": "generic",
            "conditions": {
                "adults": 2,
                "children_under_3": 0,
                "days_of_week": ["Saturday", "Sunday"],
                "time": "18:30",
            },
        },
    ]


def build_sample_config(now: Optional[datetime] = None) -> Dict[str, Any]:
    """Return a full sample config dict (targets + notification)."""
    return {
        "targets": build_sample_targets(now),
        "notification": {
            "type": "discord",
            "webhook_url_env": "DISCORD_WEBHOOK_URL",
            "channels": [
                {
                    "type": "discord",
                    "webhook_url_env": "DISCORD_WEBHOOK_URL",
                    "enabled": True,
                }
            ],
            "snooze_until": None,
        },
    }


def write_sample_config(path: str, now: Optional[datetime] = None) -> None:
    """Write the sample config to ``path`` as pretty UTF-8 JSON."""
    config = build_sample_config(now)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.write("\n")


# --------------------------------------------------------------------------- #
# Sample slots
# --------------------------------------------------------------------------- #
def _expand_dates(conditions: Dict[str, Any]) -> List[str]:
    dr = conditions.get("date_range")
    if not dr or not dr.get("start") or not dr.get("end"):
        return []
    try:
        start = datetime.strptime(dr["start"], "%Y-%m-%d").date()
        end = datetime.strptime(dr["end"], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return []
    if end < start:
        return []
    allowed = {
        _WEEKDAY_INDEX[d]
        for d in conditions.get("days_of_week", []) or []
        if d in _WEEKDAY_INDEX
    }
    dates: List[str] = []
    cur = start
    while cur <= end:
        if not allowed or cur.weekday() in allowed:
            dates.append(cur.isoformat())
        cur += timedelta(days=1)
    return dates


def _expand_times(conditions: Dict[str, Any]) -> List[str]:
    tr = conditions.get("time_range")
    if not tr or not tr.get("start") or not tr.get("end"):
        return []
    try:
        sh, sm = (int(x) for x in tr["start"].split(":"))
        eh, em = (int(x) for x in tr["end"].split(":"))
    except (ValueError, TypeError, AttributeError):
        return []
    start = sh * 60 + sm
    end = eh * 60 + em
    step = int(tr.get("step_minutes", 15)) or 15
    if step <= 0 or end < start:
        return []
    times: List[str] = []
    cur = start
    while cur <= end:
        times.append(f"{cur // 60:02d}:{cur % 60:02d}")
        cur += step
    return times


def build_sample_slots(target: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Deterministically expand a range target into varied Slot dicts.

    Availability pattern (deterministic): mostly ``unavailable`` (full), a few
    ``available`` (open) and a couple ``unknown`` so the grid shows all states.
    Returns ``[]`` for non-range (legacy single-time) targets.
    """
    conditions = target.get("conditions") or {}
    dates = _expand_dates(conditions)
    times = _expand_times(conditions)
    if not dates or not times:
        return []

    slots: List[Dict[str, Any]] = []
    for i, d in enumerate(dates):
        for j, t in enumerate(times):
            idx = i * len(times) + j
            # Deterministic spread across the three states.
            if idx % 7 == 0:
                available: Optional[bool] = True
                source = "dom"
            elif idx % 5 == 0:
                available = None
                source = "unknown"
            else:
                available = False
                source = "dom"
            slots.append(
                {"date": d, "time": t, "available": available, "source": source}
            )
    return slots


# --------------------------------------------------------------------------- #
# History seeding
# --------------------------------------------------------------------------- #
def _read_non_sample_lines(path: str) -> List[str]:
    """Return existing lines that are NOT sample-tagged (real records preserved)."""
    if not os.path.exists(path):
        return []
    kept: List[str] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    entry = json.loads(stripped)
                except json.JSONDecodeError:
                    kept.append(stripped)
                    continue
                if not entry.get(SAMPLE_TAG):
                    kept.append(stripped)
    except OSError as e:
        logger.warning("Failed to read %s: %s", path, e)
    return kept


def _write_lines(path: str, lines: List[str]) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")


def _build_latest_states(
    targets: List[Dict[str, Any]], now: datetime
) -> List[Dict[str, Any]]:
    """One latest-state record per sample target with a spread of statuses."""
    states: List[Dict[str, Any]] = []
    for i, target in enumerate(targets):
        slots = build_sample_slots(target)
        checked_at = _iso(now - timedelta(minutes=2 + i))
        error: Optional[str] = None
        available: Optional[bool] = False
        notified = False

        # Make the dashboard show every status: error / available+notified /
        # unavailable, deterministically by index.
        if i == len(targets) - 1:
            # Last target: error state.
            error = "ページ取得に失敗しました (HTTP 503 / サンプル)"
            available = None
        elif i == 0:
            # First target: available and already notified.
            available = True
            notified = True
        else:
            available = False

        states.append(
            {
                "target_name": target["name"],
                "url": target["url"],
                "available": available,
                "notified": notified,
                "checked_at": checked_at,
                "error": error,
                "slots": slots,
                SAMPLE_TAG: True,
            }
        )
    return states


def _build_check_history(
    targets: List[Dict[str, Any]], now: datetime
) -> List[Dict[str, Any]]:
    """A time-series of check events over the past ~3 days (oldest first)."""
    events: List[Dict[str, Any]] = []
    total = 48  # ~3 days at a few-hours cadence across targets
    for k in range(total):
        target = targets[k % len(targets)]
        # Spread events backwards over 72 hours.
        ts = now - timedelta(hours=(total - k) * 1.5)
        is_error = (k % 13) == 0
        available = (k % 6) == 0
        state_changed = (k % 6) == 0 or (k % 6) == 1
        notified = available and target.get("notify", True)
        if is_error:
            summary = "取得失敗 (サンプル)"
            avail_val: Optional[bool] = None
            error: Optional[str] = "一時的なネットワークエラー (サンプル)"
        elif available:
            summary = "空きあり (サンプル)"
            avail_val = True
            error = None
        else:
            summary = "満席 (サンプル)"
            avail_val = False
            error = None
        events.append(
            {
                "checked_at": _iso(ts),
                "target_name": target["name"],
                "url": target["url"],
                "available": avail_val,
                "summary": summary,
                "notified": notified,
                "state_changed": state_changed,
                "error": error,
                "slots": [],
                SAMPLE_TAG: True,
            }
        )
    return events


def _build_notification_history(
    targets: List[Dict[str, Any]], now: datetime
) -> List[Dict[str, Any]]:
    """A handful of notification events (mix success / skipped), oldest first."""
    notifiable = [t for t in targets if t.get("notify", True)]
    events: List[Dict[str, Any]] = []
    count = 6
    for k in range(count):
        target = notifiable[k % len(notifiable)] if notifiable else targets[0]
        ts = now - timedelta(hours=(count - k) * 5)
        skipped = (k % 3) == 2  # every third one snoozed/skipped
        success = not skipped
        events.append(
            {
                "sent_at": _iso(ts),
                "target_name": target["name"],
                "url": target["url"],
                "summary": "空き枠を検知しました (サンプル)",
                "success": success,
                "skipped": skipped,
                "error": None if success else "スヌーズ中のためスキップ (サンプル)",
                SAMPLE_TAG: True,
            }
        )
    return events


def seed_history(
    history_dir: str = "logs",
    force: bool = False,
    now: Optional[datetime] = None,
    targets: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, int]:
    """Idempotently seed the three history JSONL files with sample records.

    Existing non-sample (real) records are preserved; previously-written sample
    records are replaced. ``force`` only affects callers that gate on it; the
    seeding itself is always idempotent here.
    """
    now = now or _now()
    targets = targets if targets is not None else build_sample_targets(now)

    history_path = os.path.join(history_dir, _HISTORY_FILE)
    check_path = os.path.join(history_dir, _CHECK_HISTORY_FILE)
    notif_path = os.path.join(history_dir, _NOTIFICATION_HISTORY_FILE)

    latest = _build_latest_states(targets, now)
    checks = _build_check_history(targets, now)
    notifs = _build_notification_history(targets, now)

    def _serialize(records: List[Dict[str, Any]]) -> List[str]:
        return [json.dumps(r, ensure_ascii=False) for r in records]

    _write_lines(
        history_path, _read_non_sample_lines(history_path) + _serialize(latest)
    )
    _write_lines(
        check_path, _read_non_sample_lines(check_path) + _serialize(checks)
    )
    _write_lines(
        notif_path, _read_non_sample_lines(notif_path) + _serialize(notifs)
    )

    return {
        "latest": len(latest),
        "checks": len(checks),
        "notifications": len(notifs),
        "config_targets": len(targets),
    }


def seed_all(
    config_path: str = "config.sample.json",
    history_dir: str = "logs",
    force: bool = False,
    now: Optional[datetime] = None,
) -> Dict[str, int]:
    """Write the sample config (if missing, or always when ``force``) and seed history."""
    now = now or _now()
    if force or not os.path.exists(config_path):
        write_sample_config(config_path, now)
    targets = build_sample_targets(now)
    summary = seed_history(history_dir=history_dir, force=force, now=now, targets=targets)
    logger.info(
        "Seeded sample data: config=%s targets=%d latest=%d checks=%d notifications=%d",
        config_path,
        summary["config_targets"],
        summary["latest"],
        summary["checks"],
        summary["notifications"],
    )
    return summary
