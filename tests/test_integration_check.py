"""Integration tests for the booking check logic against a mock site.

The ``fixture_server`` (see ``conftest.py``) serves static HTML fixtures over a
local HTTP server. We point a :class:`Target` at those URLs and exercise the
real ``check_target`` entry point end to end:

* the generic (httpx + keyword) path, and
* the TableCheck (real Chromium via Playwright) path.

TableCheck tests require a real Chromium browser and are marked ``playwright``
so they can be deselected in environments without one
(``pytest -m "not playwright"``).
"""

import pytest

from booking_monitor.checker import check_target
from booking_monitor.config import Conditions, Target


def _target(url: str, *, site_type: str) -> Target:
    """Build a Target pointing at a fixture URL."""
    return Target(
        name=f"mock-{site_type}",
        url=url,
        interval_seconds=300,
        available_keywords=["空きあり"],
        unavailable_keywords=["満席"],
        notify=False,
        site_type=site_type,
        conditions=Conditions(
            adults=2,
            children_under_3=0,
            days_of_week=["Saturday", "Sunday"],
            time="15:00",
        ),
    )


# --- generic path (no browser required) ---------------------------------


@pytest.mark.asyncio
async def test_generic_available(fixture_server):
    target = _target(
        f"{fixture_server}/generic_available.html", site_type="generic"
    )
    available, summary, _slots = await check_target(target)
    assert available is True
    assert "空きあり" in summary


@pytest.mark.asyncio
async def test_generic_unavailable(fixture_server):
    target = _target(
        f"{fixture_server}/generic_unavailable.html", site_type="generic"
    )
    available, summary, _slots = await check_target(target)
    assert available is False
    assert "満席" in summary


# --- tablecheck path (real Chromium) -------------------------------------


@pytest.mark.playwright
@pytest.mark.asyncio
async def test_tablecheck_available(fixture_server):
    target = _target(
        f"{fixture_server}/tablecheck_available.html", site_type="tablecheck"
    )
    available, summary, _slots = await check_target(target)
    assert available is True
    assert summary


@pytest.mark.playwright
@pytest.mark.asyncio
async def test_tablecheck_unavailable(fixture_server):
    target = _target(
        f"{fixture_server}/tablecheck_unavailable.html", site_type="tablecheck"
    )
    available, summary, _slots = await check_target(target)
    assert available is False
    assert summary
