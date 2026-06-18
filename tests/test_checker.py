"""Unit tests for the matcher / availability logic exercised via
``booking_monitor.checker.check_target``.

``httpx`` is mocked (on the ``GenericSite`` plugin module, where the generic
HTTP path now lives) so it runs without network access, and
``TableCheckSite.check`` is patched so ``check_target`` routing is verified
without launching a browser.
"""

from unittest.mock import AsyncMock, patch

import pytest

from booking_monitor.checker import check_target
from booking_monitor.config import Target
from booking_monitor.sites import generic as generic_site


def _target(*, site_type="generic", available=None, unavailable=None):
    return Target(
        name="mock",
        url="https://example.com/booking",
        interval_seconds=300,
        available_keywords=["空きあり"] if available is None else available,
        unavailable_keywords=["満席"] if unavailable is None else unavailable,
        notify=False,
        site_type=site_type,
    )


class _FakeResp:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


class _FakeAsyncClient:
    def __init__(self, *, resp=None, exc=None):
        self._resp = resp
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def get(self, url, headers=None):
        if self._exc is not None:
            raise self._exc
        return self._resp


def _patch_client(*, text=None, exc=None):
    resp = _FakeResp(text) if text is not None else None
    return patch.object(
        generic_site.httpx,
        "AsyncClient",
        lambda *a, **k: _FakeAsyncClient(resp=resp, exc=exc),
    )


@pytest.mark.asyncio
async def test_generic_available_keyword():
    with _patch_client(text="本日空きあり"):
        available, summary = await check_target(_target())
    assert available is True
    assert "空きあり" in summary


@pytest.mark.asyncio
async def test_generic_unavailable_takes_precedence():
    # both keywords present; the unavailable keyword must win
    with _patch_client(text="満席 空きあり"):
        available, summary = await check_target(_target())
    assert available is False
    assert "満席" in summary


@pytest.mark.asyncio
async def test_generic_no_match():
    with _patch_client(text="no keywords here"):
        available, summary = await check_target(_target())
    assert available is False
    assert summary == "No matching keywords found"


@pytest.mark.asyncio
async def test_generic_http_failure_raises_runtimeerror():
    with _patch_client(exc=ValueError("boom")):
        with pytest.raises(RuntimeError) as ei:
            await check_target(_target())
    assert "HTTP fetch failed" in str(ei.value)


@pytest.mark.asyncio
async def test_check_target_routes_to_tablecheck():
    with patch(
        "booking_monitor.sites.tablecheck.TableCheckSite.check",
        new=AsyncMock(return_value=(True, "stub")),
    ) as mock_check:
        result = await check_target(_target(site_type="tablecheck"))
    assert result == (True, "stub")
    mock_check.assert_awaited_once()
