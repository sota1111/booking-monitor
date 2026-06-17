"""Unit tests for TableCheckSite._find_available_weekend_slots using a mocked page.

No real browser is launched; the Playwright ``page`` is replaced with mocks so
the DOM-scanning logic can be exercised in any environment.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from booking_monitor.config import Target
from booking_monitor.sites.tablecheck import TableCheckSite


def _site():
    target = Target(
        name="mock",
        url="https://example.com",
        interval_seconds=300,
        available_keywords=["空きあり"],
        unavailable_keywords=["満席"],
        notify=False,
        site_type="tablecheck",
    )
    return TableCheckSite(target)


def _element(*, aria=None, text=None):
    el = MagicMock()
    el.get_attribute = AsyncMock(return_value=aria)
    el.inner_text = AsyncMock(return_value=text)
    return el


def _locator(elements):
    loc = MagicMock()
    loc.all = AsyncMock(return_value=list(elements))
    return loc


@pytest.mark.asyncio
async def test_find_slots_returns_aria_labels():
    page = MagicMock()
    page.locator = MagicMock(return_value=_locator([_element(aria=" Sat 15:00 ")]))
    site = _site()
    result = await site._find_available_weekend_slots(page, ["Saturday"], "15:00")
    assert result == ["Sat 15:00"]


@pytest.mark.asyncio
async def test_find_slots_uses_later_selector_when_first_empty():
    page = MagicMock()
    page.locator = MagicMock(
        side_effect=[_locator([]), _locator([_element(aria="Sun 12:00")])]
    )
    site = _site()
    result = await site._find_available_weekend_slots(page, ["Sunday"], "12:00")
    assert result == ["Sun 12:00"]


@pytest.mark.asyncio
async def test_find_slots_returns_empty_when_no_elements():
    page = MagicMock()
    page.locator = MagicMock(return_value=_locator([]))
    site = _site()
    result = await site._find_available_weekend_slots(page, ["Saturday"], "15:00")
    assert result == []


@pytest.mark.asyncio
async def test_find_slots_swallows_errors():
    page = MagicMock()
    page.locator = MagicMock(side_effect=RuntimeError("dom blew up"))
    site = _site()
    result = await site._find_available_weekend_slots(page, ["Saturday"], "15:00")
    assert result == []
