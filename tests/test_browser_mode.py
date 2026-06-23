"""Unit tests for BrowserManager ephemeral vs persistent modes (SOT-1141).

No real Chromium is launched: ``async_playwright`` is replaced with async fakes so
both launch modes can be exercised in any environment. These tests are NOT marked
``playwright`` (they require no browser binary).
"""

import pytest

import booking_monitor.sites.browser as browser_mod
from booking_monitor.sites.browser import (
    BrowserManager,
    browser_manager_from_env,
)


class FakePage:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FakeContext:
    def __init__(self, *, storage_state=None) -> None:
        self.storage_state = storage_state
        self.closed = False
        self.pages = []

    async def new_page(self) -> FakePage:
        page = FakePage()
        self.pages.append(page)
        return page

    async def close(self) -> None:
        self.closed = True


class FakeBrowser:
    def __init__(self) -> None:
        self.contexts = []
        self.closed = False

    def is_connected(self) -> bool:
        return not self.closed

    async def new_context(self, storage_state=None) -> FakeContext:
        ctx = FakeContext(storage_state=storage_state)
        self.contexts.append(ctx)
        return ctx

    async def close(self) -> None:
        self.closed = True


class FakeChromium:
    def __init__(self) -> None:
        self.launch_calls = []
        self.persistent_calls = []
        self.browsers = []
        self.persistent_contexts = []

    async def launch(self, headless=True):
        self.launch_calls.append({"headless": headless})
        browser = FakeBrowser()
        self.browsers.append(browser)
        return browser

    async def launch_persistent_context(self, user_data_dir, headless=True):
        self.persistent_calls.append(
            {"user_data_dir": user_data_dir, "headless": headless}
        )
        ctx = FakeContext()
        self.persistent_contexts.append(ctx)
        return ctx


class FakePlaywright:
    def __init__(self) -> None:
        self.chromium = FakeChromium()
        self.stopped = False

    async def stop(self) -> None:
        self.stopped = True


class FakeAsyncPlaywrightCM:
    """Mimics the object returned by ``async_playwright()`` (has ``.start()``)."""

    def __init__(self, playwright: FakePlaywright) -> None:
        self._playwright = playwright

    async def start(self) -> FakePlaywright:
        return self._playwright


@pytest.fixture
def fake_playwright(monkeypatch):
    playwright = FakePlaywright()
    monkeypatch.setattr(
        browser_mod,
        "async_playwright",
        lambda: FakeAsyncPlaywrightCM(playwright),
    )
    return playwright


# --- factory: env parsing ------------------------------------------------------


def test_from_env_defaults_to_ephemeral(monkeypatch):
    monkeypatch.delenv("BOOKING_BROWSER_MODE", raising=False)
    monkeypatch.delenv("BOOKING_HEADFUL", raising=False)
    mgr = browser_manager_from_env()
    assert mgr.mode == "ephemeral"
    assert mgr._headless is True


def test_from_env_persistent_expands_user_data_dir(monkeypatch, tmp_path):
    profile = tmp_path / "profile"
    monkeypatch.setenv("BOOKING_BROWSER_MODE", "persistent")
    monkeypatch.setenv("BOOKING_USER_DATA_DIR", str(profile))
    mgr = browser_manager_from_env()
    assert mgr.mode == "persistent"
    assert mgr._user_data_dir == str(profile)
    assert profile.exists()  # created on construction


def test_from_env_headful_sets_headless_false(monkeypatch):
    monkeypatch.setenv("BOOKING_BROWSER_MODE", "ephemeral")
    monkeypatch.setenv("BOOKING_HEADFUL", "1")
    mgr = browser_manager_from_env()
    assert mgr._headless is False


def test_from_env_unknown_mode_falls_back_to_ephemeral(monkeypatch):
    monkeypatch.setenv("BOOKING_BROWSER_MODE", "bogus")
    mgr = browser_manager_from_env()
    assert mgr.mode == "ephemeral"


def test_persistent_without_user_data_dir_raises():
    with pytest.raises(ValueError):
        BrowserManager(mode="persistent", user_data_dir="")


def test_unknown_mode_arg_falls_back_to_ephemeral():
    mgr = BrowserManager(mode="bogus")
    assert mgr.mode == "ephemeral"


# --- ephemeral mode behavior (unchanged) ---------------------------------------


async def test_ephemeral_creates_fresh_context_per_page(fake_playwright):
    mgr = BrowserManager(mode="ephemeral")

    async with mgr.new_page(storage_state={"k": 1}) as page:
        assert page is not None
    async with mgr.new_page(storage_state={"k": 2}) as page:
        assert page is not None

    chromium = fake_playwright.chromium
    # One shared browser, two contexts (one per new_page), each closed after use.
    assert len(chromium.launch_calls) == 1
    browser = chromium.browsers[0]
    assert len(browser.contexts) == 2
    assert all(ctx.closed for ctx in browser.contexts)
    assert [ctx.storage_state for ctx in browser.contexts] == [{"k": 1}, {"k": 2}]

    await mgr.close()
    assert browser.closed
    assert fake_playwright.stopped


# --- persistent mode behavior (方式①) -----------------------------------------


async def test_persistent_reuses_one_context_and_closes_only_pages(
    fake_playwright, tmp_path
):
    profile = tmp_path / "p"
    mgr = BrowserManager(
        mode="persistent", headless=False, user_data_dir=str(profile)
    )

    async with mgr.new_page() as page1:
        first_page = page1
    async with mgr.new_page() as page2:
        second_page = page2

    chromium = fake_playwright.chromium
    # launch_persistent_context called exactly once, with expanded dir + headless flag.
    assert len(chromium.persistent_calls) == 1
    assert chromium.persistent_calls[0]["user_data_dir"] == str(profile)
    assert chromium.persistent_calls[0]["headless"] is False
    assert len(chromium.launch_calls) == 0  # never uses the ephemeral browser

    context = chromium.persistent_contexts[0]
    # Both pages came from the SAME persistent context...
    assert len(context.pages) == 2
    # ...and only the pages were closed; the context stayed alive across checks.
    assert first_page.closed and second_page.closed
    assert context.closed is False

    await mgr.close()
    assert context.closed  # closed on shutdown
    assert fake_playwright.stopped


async def test_persistent_ignores_storage_state(fake_playwright, tmp_path):
    mgr = BrowserManager(
        mode="persistent", user_data_dir=str(tmp_path / "p")
    )
    # storage_state is accepted but ignored; no crash, page still yielded.
    async with mgr.new_page(storage_state={"should": "be ignored"}) as page:
        assert page is not None
    await mgr.close()


async def test_close_is_idempotent(fake_playwright, tmp_path):
    mgr = BrowserManager(mode="persistent", user_data_dir=str(tmp_path / "p"))
    async with mgr.new_page() as _:
        pass
    await mgr.close()
    await mgr.close()  # second close must not raise
