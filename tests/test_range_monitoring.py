"""Tests for range-based monitoring (SOT-833): config schema, slot expansion,
grid model, and TableCheck per-slot mapping."""

import json

import pytest

from booking_monitor.config import Conditions, DateRange, TimeRange, load_config
from booking_monitor.sites.tablecheck import TableCheckSite
from booking_monitor.slots import build_slot_grid, expand_slots, has_range

# --- config parsing -------------------------------------------------------


def test_load_config_parses_ranges(tmp_path):
    cfg = {
        "targets": [
            {
                "name": "t1",
                "url": "https://example.com",
                "available_keywords": ["空きあり"],
                "unavailable_keywords": ["満席"],
                "notify": True,
                "site_type": "tablecheck",
                "conditions": {
                    "adults": 2,
                    "date_range": {"start": "2026-06-20", "end": "2026-06-21"},
                    "time_range": {
                        "start": "12:00",
                        "end": "13:00",
                        "step_minutes": 15,
                    },
                },
            }
        ],
        "notification": {"type": "discord", "webhook_url_env": "DISCORD_WEBHOOK_URL"},
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")

    config = load_config(str(path))
    conds = config.targets[0].conditions
    assert conds.date_range == DateRange(start="2026-06-20", end="2026-06-21")
    assert conds.time_range == TimeRange(start="12:00", end="13:00", step_minutes=15)


def test_load_config_backward_compatible(tmp_path):
    """A legacy config without ranges still loads (date_range/time_range None)."""
    cfg = {
        "targets": [
            {
                "name": "legacy",
                "url": "https://example.com",
                "available_keywords": ["空きあり"],
                "unavailable_keywords": ["満席"],
                "notify": True,
                "conditions": {"days_of_week": ["Saturday"], "time": "15:00"},
            }
        ],
        "notification": {"type": "discord"},
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")

    config = load_config(str(path))
    conds = config.targets[0].conditions
    assert conds.date_range is None
    assert conds.time_range is None
    assert conds.time == "15:00"


# --- slot expansion -------------------------------------------------------


def test_expand_slots_and_search_product():
    conds = Conditions(
        date_range=DateRange(start="2026-06-20", end="2026-06-21"),
        time_range=TimeRange(start="12:00", end="12:30", step_minutes=15),
    )
    slots = expand_slots(conds)
    # 2 days x 3 times (12:00, 12:15, 12:30) = 6 slots
    assert len(slots) == 6
    assert ("2026-06-20", "12:00") in slots
    assert ("2026-06-21", "12:30") in slots
    assert has_range(conds) is True


def test_expand_slots_filters_days_of_week():
    # 2026-06-20 is Sat, 2026-06-21 is Sun, 2026-06-22 is Mon.
    conds = Conditions(
        days_of_week=["Sunday"],
        date_range=DateRange(start="2026-06-20", end="2026-06-22"),
        time_range=TimeRange(start="12:00", end="12:00", step_minutes=15),
    )
    slots = expand_slots(conds)
    assert slots == [("2026-06-21", "12:00")]


def test_expand_slots_legacy_returns_empty():
    """Legacy days_of_week+time (no date_range) yields no concrete slots."""
    conds = Conditions(days_of_week=["Saturday"], time="15:00")
    assert expand_slots(conds) == []
    assert has_range(conds) is False


def test_expand_slots_invalid_range_is_safe():
    conds = Conditions(
        date_range=DateRange(start="2026-06-21", end="2026-06-20"),  # end < start
        time_range=TimeRange(start="12:00", end="13:00", step_minutes=15),
    )
    assert expand_slots(conds) == []


# --- grid model -----------------------------------------------------------


def test_build_slot_grid_shapes_and_counts():
    slots = [
        {"date": "2026-06-20", "time": "12:00", "available": True, "source": "dom"},
        {"date": "2026-06-20", "time": "12:15", "available": False, "source": "dom"},
        {"date": "2026-06-21", "time": "12:00", "available": None, "source": "unknown"},
    ]
    grid = build_slot_grid(slots)
    assert grid["dates"] == ["2026-06-20", "2026-06-21"]
    assert grid["times"] == ["12:00", "12:15"]
    assert grid["available_count"] == 1
    assert grid["total"] == 3
    assert grid["cells"]["2026-06-20"]["12:00"] == "available"
    assert grid["cells"]["2026-06-20"]["12:15"] == "unavailable"
    assert grid["cells"]["2026-06-21"]["12:00"] == "unknown"


def test_build_slot_grid_empty_returns_none():
    assert build_slot_grid([]) is None


# --- tablecheck per-slot mapping -----------------------------------------


def _site():
    from booking_monitor.config import Target

    target = Target(
        name="tc",
        url="https://example.com",
        interval_seconds=300,
        available_keywords=["空きあり"],
        unavailable_keywords=["満席"],
        notify=False,
        site_type="tablecheck",
    )
    return TableCheckSite(target)


def test_build_range_slots_marks_dom_matches_available():
    site = _site()
    desired = [("2026-06-20", "12:00"), ("2026-06-20", "12:15")]
    slots = site._build_range_slots(
        desired, page_text="カレンダー", available_labels=["12:00 空きあり"]
    )
    by_time = {s["time"]: s for s in slots}
    assert by_time["12:00"]["available"] is True
    assert by_time["12:00"]["source"] == "dom"
    assert by_time["12:15"]["available"] is False


def test_build_range_slots_keyword_fallback_when_no_labels():
    site = _site()
    desired = [("2026-06-20", "12:00")]
    # No DOM labels, page says 満席 -> all slots unavailable via keyword.
    slots = site._build_range_slots(
        desired, page_text="本日は満席です", available_labels=[]
    )
    assert slots[0]["available"] is False
    assert slots[0]["source"] == "keyword"


def test_build_range_slots_unknown_when_undecided():
    site = _site()
    desired = [("2026-06-20", "12:00")]
    slots = site._build_range_slots(
        desired, page_text="no signal", available_labels=[]
    )
    assert slots[0]["available"] is None
    assert slots[0]["source"] == "unknown"


def test_range_summary_reports_counts():
    slots = [
        {"date": "2026-06-20", "time": "12:00", "available": True, "source": "dom"},
        {"date": "2026-06-20", "time": "12:15", "available": False, "source": "dom"},
    ]
    summary = TableCheckSite._range_summary(slots)
    assert "1/2" in summary


@pytest.mark.asyncio
async def test_monitor_notifies_on_any_available_slot(monkeypatch, tmp_path):
    """run_checks notifies when any range slot is available (#4)."""
    from booking_monitor.config import Config, Notification, Target
    from booking_monitor.history import History
    from booking_monitor.services import monitor_service

    target = Target(
        name="range-tc",
        url="https://example.com",
        interval_seconds=300,
        available_keywords=["空きあり"],
        unavailable_keywords=["満席"],
        notify=True,
        site_type="tablecheck",
        conditions=Conditions(
            date_range=DateRange(start="2026-06-20", end="2026-06-20"),
            time_range=TimeRange(start="12:00", end="12:15", step_minutes=15),
        ),
    )
    config = Config(
        targets=[target],
        notification=Notification(type="discord", webhook_url_env="X"),
    )

    range_slots = [
        {"date": "2026-06-20", "time": "12:00", "available": True, "source": "dom"},
        {"date": "2026-06-20", "time": "12:15", "available": False, "source": "dom"},
    ]

    async def fake_check(_target, browser_manager=None):
        return True, "空き 1/2 スロット", range_slots

    sent = {}

    def fake_send(self, tgt, summary):
        sent["summary"] = summary

    class _NoBrowser:
        async def close(self):
            return None

    monkeypatch.setattr(monitor_service, "check_target", fake_check)
    monkeypatch.setattr(monitor_service, "BrowserManager", lambda: _NoBrowser())
    monkeypatch.setattr(
        "booking_monitor.notifier.Notifier.send", fake_send, raising=True
    )

    history = History(path=str(tmp_path / "history.jsonl"))
    results = await monitor_service.run_checks(config, history)

    assert results[0]["available"] is True
    assert results[0]["slots"] == range_slots
    assert sent.get("summary") == "空き 1/2 スロット"
    # latest state persisted the slots for the dashboard grid
    state = history.get_last_state("range-tc")
    assert state["slots"] == range_slots
