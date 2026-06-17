"""Tests for structure-change detection: retry with backoff, screenshot on
failure, and distinguishing a structure change from a normal result."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from booking_monitor.sites._resilience import wait_for_required_selector
from booking_monitor.sites.exceptions import StructureChangeError


def _make_page(side_effects, screenshot_ok=True):
    """Build a fake async Playwright page.

    ``side_effects`` is the list of behaviors for successive
    ``wait_for_selector`` calls (an exception instance to raise, or a value to
    return).
    """
    page = MagicMock()
    page.wait_for_selector = AsyncMock(side_effect=side_effects)
    if screenshot_ok:
        page.screenshot = AsyncMock(return_value=None)
    else:
        page.screenshot = AsyncMock(side_effect=OSError("disk full"))
    return page


@pytest.mark.asyncio
async def test_retries_then_succeeds(monkeypatch):
    """Times out twice, then succeeds: returns the element, no exception."""
    sleeps = []
    monkeypatch.setattr(
        "booking_monitor.sites._resilience.asyncio.sleep",
        AsyncMock(side_effect=lambda d: sleeps.append(d)),
    )
    sentinel = object()
    page = _make_page([PlaywrightTimeoutError("t"), PlaywrightTimeoutError("t"), sentinel])

    result = await wait_for_required_selector(
        page, "[class*='calendar']", url="https://example.com", retries=3
    )

    assert result is sentinel
    assert page.wait_for_selector.await_count == 3
    # Exponential backoff between the two failures: 0.5 * 2**0, 0.5 * 2**1
    assert sleeps == [0.5, 1.0]
    page.screenshot.assert_not_awaited()


@pytest.mark.asyncio
async def test_all_retries_fail_saves_screenshot_and_raises(monkeypatch, tmp_path):
    """All attempts time out: screenshot is saved and StructureChangeError raised."""
    monkeypatch.setattr(
        "booking_monitor.sites._resilience.asyncio.sleep", AsyncMock()
    )
    page = _make_page([PlaywrightTimeoutError("t")] * 3)

    with pytest.raises(StructureChangeError) as exc:
        await wait_for_required_selector(
            page,
            "[class*='calendar']",
            url="https://example.com",
            retries=3,
            screenshot_dir=str(tmp_path / "shots"),
        )

    page.screenshot.assert_awaited_once()
    err = exc.value
    assert err.selector == "[class*='calendar']"
    assert err.url == "https://example.com"
    assert err.screenshot_path is not None
    assert err.screenshot_path.endswith(".png")


@pytest.mark.asyncio
async def test_screenshot_failure_does_not_mask_structure_error(monkeypatch, tmp_path):
    """If screenshot capture fails, StructureChangeError is still raised."""
    monkeypatch.setattr(
        "booking_monitor.sites._resilience.asyncio.sleep", AsyncMock()
    )
    page = _make_page([PlaywrightTimeoutError("t")] * 2, screenshot_ok=False)

    with pytest.raises(StructureChangeError) as exc:
        await wait_for_required_selector(
            page,
            "[class*='calendar']",
            retries=2,
            screenshot_dir=str(tmp_path / "shots"),
        )

    assert exc.value.screenshot_path is None


@pytest.mark.asyncio
async def test_found_immediately_no_screenshot_no_sleep(monkeypatch):
    """Required element present on first try: no retry, no screenshot, no error."""
    sleep_mock = AsyncMock()
    monkeypatch.setattr(
        "booking_monitor.sites._resilience.asyncio.sleep", sleep_mock
    )
    sentinel = object()
    page = _make_page([sentinel])

    result = await wait_for_required_selector(page, "[class*='calendar']", retries=3)

    assert result is sentinel
    assert page.wait_for_selector.await_count == 1
    sleep_mock.assert_not_awaited()
    page.screenshot.assert_not_awaited()
