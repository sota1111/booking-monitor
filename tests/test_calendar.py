"""Unit tests for the availability calendar overview aggregation (SOT-886)."""

from booking_monitor.slots import build_calendar_overview, build_slot_grid


def _grid(*slots):
    """Build a grid (build_slot_grid output) from (date, time, available) tuples."""
    return build_slot_grid(
        [{"date": d, "time": t, "available": a} for (d, t, a) in slots]
    )


def test_no_targets_with_grid_returns_none():
    assert build_calendar_overview([]) is None
    assert build_calendar_overview([{"name": "x", "grid": None}]) is None


def test_any_available_makes_cell_available():
    targets = [
        {"name": "A", "grid": _grid(("2026-07-01", "11:00", False))},
        {"name": "B", "grid": _grid(("2026-07-01", "11:00", True))},
    ]
    overview = build_calendar_overview(targets)
    assert overview is not None
    cell = overview["cells"]["2026-07-01"]["11:00"]
    assert cell["state"] == "available"
    assert cell["available_targets"] == 1
    assert cell["total_targets"] == 2
    assert overview["available_count"] == 1
    assert overview["target_count"] == 2


def test_all_known_none_available_is_unavailable():
    targets = [
        {"name": "A", "grid": _grid(("2026-07-01", "11:00", False))},
        {"name": "B", "grid": _grid(("2026-07-01", "11:00", False))},
    ]
    overview = build_calendar_overview(targets)
    cell = overview["cells"]["2026-07-01"]["11:00"]
    assert cell["state"] == "unavailable"
    assert cell["available_targets"] == 0
    assert overview["available_count"] == 0


def test_all_unknown_is_unknown():
    targets = [{"name": "A", "grid": _grid(("2026-07-01", "11:00", None))}]
    overview = build_calendar_overview(targets)
    cell = overview["cells"]["2026-07-01"]["11:00"]
    assert cell["state"] == "unknown"


def test_axes_are_union_and_sorted():
    targets = [
        {"name": "A", "grid": _grid(
            ("2026-07-02", "12:00", True),
            ("2026-07-01", "11:00", False),
        )},
        {"name": "B", "grid": _grid(("2026-07-01", "09:00", True))},
    ]
    overview = build_calendar_overview(targets)
    assert overview["dates"] == ["2026-07-01", "2026-07-02"]
    assert overview["times"] == ["09:00", "11:00", "12:00"]
    # available_count counts cells (not targets): 09:00 and 12:00 are available.
    assert overview["available_count"] == 2


def test_targets_without_grid_are_ignored():
    targets = [
        {"name": "A", "grid": None},
        {"name": "B", "grid": _grid(("2026-07-01", "11:00", True))},
    ]
    overview = build_calendar_overview(targets)
    assert overview["target_count"] == 1
    assert overview["cells"]["2026-07-01"]["11:00"]["total_targets"] == 1
