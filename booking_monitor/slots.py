"""Slot expansion and grid model for range-based monitoring (SOT-833).

A "slot" is a concrete ``(date, time)`` pair the user wants monitored. The user
specifies a *date range* and a *time range* (with a step, default 15 min); we
expand the AND product of the two into individual slots, optionally filtered by
``days_of_week``. The dashboard then renders per-slot availability as a grid so
the human can see *when* a target is open and *when* it is full.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

# Map English weekday names (as used in config ``days_of_week``) to
# ``date.weekday()`` indices (Monday=0).
_WEEKDAY_INDEX = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6,
}


@dataclass(frozen=True)
class Slot:
    """A single monitored ``(date, time)`` cell and its availability.

    ``available`` is ``True`` (open), ``False`` (full), or ``None`` (unknown /
    not yet determined). ``source`` records how availability was decided
    (``"dom"``, ``"keyword"``, or ``"unknown"``).
    """

    date: str  # YYYY-MM-DD
    time: str  # HH:MM
    available: Optional[bool] = None
    source: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date,
            "time": self.time,
            "available": self.available,
            "source": self.source,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Slot":
        return Slot(
            date=d.get("date", ""),
            time=d.get("time", ""),
            available=d.get("available"),
            source=d.get("source", "unknown"),
        )


def _parse_date(value: str) -> Optional[date]:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _parse_time(value: str) -> Optional[int]:
    """Return minutes-since-midnight for ``HH:MM`` (or ``None`` if invalid)."""
    try:
        t = datetime.strptime(value, "%H:%M")
    except (ValueError, TypeError):
        return None
    return t.hour * 60 + t.minute


def _expand_dates(conditions: Any) -> List[str]:
    """Concrete dates from ``date_range``, filtered by ``days_of_week``."""
    date_range = getattr(conditions, "date_range", None)
    if not date_range:
        return []
    start = _parse_date(date_range.start)
    end = _parse_date(date_range.end)
    if start is None or end is None or end < start:
        return []

    days_of_week = getattr(conditions, "days_of_week", None) or []
    allowed = {
        _WEEKDAY_INDEX[d] for d in days_of_week if d in _WEEKDAY_INDEX
    }

    dates: List[str] = []
    cur = start
    while cur <= end:
        if not allowed or cur.weekday() in allowed:
            dates.append(cur.isoformat())
        cur += timedelta(days=1)
    return dates


def _expand_times(conditions: Any) -> List[str]:
    """Concrete ``HH:MM`` times from ``time_range`` (step), else legacy ``time``."""
    time_range = getattr(conditions, "time_range", None)
    if time_range:
        start = _parse_time(time_range.start)
        end = _parse_time(time_range.end)
        step = getattr(time_range, "step_minutes", 15) or 15
        if start is None or end is None or step <= 0 or end < start:
            return []
        times: List[str] = []
        cur = start
        while cur <= end:
            times.append(f"{cur // 60:02d}:{cur % 60:02d}")
            cur += step
        return times

    legacy_time = getattr(conditions, "time", "") or ""
    return [legacy_time] if legacy_time else []


def expand_slots(conditions: Any) -> List[Tuple[str, str]]:
    """Expand conditions into ``(date, time)`` pairs (AND search).

    Returns the product of the concrete dates (from ``date_range`` filtered by
    ``days_of_week``) and concrete times (from ``time_range`` step, or the
    legacy single ``time``). Returns ``[]`` when a range is not fully specified
    (e.g. legacy ``days_of_week``-only configs), in which case callers fall back
    to the existing single-status behaviour.
    """
    if conditions is None:
        return []
    dates = _expand_dates(conditions)
    times = _expand_times(conditions)
    if not dates or not times:
        return []
    return [(d, t) for d in dates for t in times]


def has_range(conditions: Any) -> bool:
    """True when the target uses range-based monitoring (date_range + times)."""
    return bool(expand_slots(conditions))


def build_slot_grid(slots: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Build a date x time grid view model from stored slot dicts.

    Returns ``{dates, times, cells, available_count, total}`` where ``cells`` is
    ``{date: {time: "available"|"unavailable"|"unknown"}}``. Returns ``None`` when
    there are no slots so the template can fall back to the single-status badge.
    """
    if not slots:
        return None

    dates: List[str] = []
    times: List[str] = []
    cells: Dict[str, Dict[str, str]] = {}
    available_count = 0

    for raw in slots:
        slot = Slot.from_dict(raw) if not isinstance(raw, Slot) else raw
        if slot.date not in cells:
            cells[slot.date] = {}
            dates.append(slot.date)
        if slot.time not in times:
            times.append(slot.time)

        if slot.available is True:
            state = "available"
            available_count += 1
        elif slot.available is False:
            state = "unavailable"
        else:
            state = "unknown"
        cells[slot.date][slot.time] = state

    dates.sort()
    times.sort()

    return {
        "dates": dates,
        "times": times,
        "cells": cells,
        "available_count": available_count,
        "total": len(slots),
    }


def build_calendar_overview(targets: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Aggregate every target's per-slot grid into one day×time calendar overview.

    ``targets`` is the list of target view dicts (each with a ``name`` and a ``grid``
    produced by :func:`build_slot_grid`, or ``None``). The union of all dates and times
    across targets that have a grid forms the calendar axes. For each ``(date, time)``
    cell, availability is aggregated across the targets that monitor it:

    - ``"available"`` if ANY target is open there (``available_targets`` counts how many);
    - ``"unavailable"`` if at least one target reports the cell but none is open;
    - ``"unknown"`` if every reporting target is unknown.

    Returns ``{dates, times, cells, available_count, target_count}`` where ``cells`` is
    ``{date: {time: {state, available_targets, total_targets}}}``. Returns ``None`` when
    no target has a grid, so the page can render an empty state.
    """
    grids = [t["grid"] for t in targets if t.get("grid")]
    if not grids:
        return None

    dates_set: set[str] = set()
    times_set: set[str] = set()
    # (date, time) -> [available_targets, total_targets, known_targets]
    tally: Dict[Tuple[str, str], List[int]] = {}

    for grid in grids:
        cells = grid.get("cells", {})
        for d, row in cells.items():
            dates_set.add(d)
            for t, state in row.items():
                times_set.add(t)
                entry = tally.setdefault((d, t), [0, 0, 0])
                entry[1] += 1  # total targets reporting this cell
                if state == "available":
                    entry[0] += 1
                    entry[2] += 1
                elif state == "unavailable":
                    entry[2] += 1

    dates = sorted(dates_set)
    times = sorted(times_set)

    out_cells: Dict[str, Dict[str, Dict[str, Any]]] = {}
    available_count = 0
    for (d, t), (avail, total, known) in tally.items():
        if avail > 0:
            state = "available"
            available_count += 1
        elif known > 0:
            state = "unavailable"
        else:
            state = "unknown"
        out_cells.setdefault(d, {})[t] = {
            "state": state,
            "available_targets": avail,
            "total_targets": total,
        }

    return {
        "dates": dates,
        "times": times,
        "cells": out_cells,
        "available_count": available_count,
        "target_count": len(grids),
    }
