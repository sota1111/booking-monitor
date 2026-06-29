"""Unit tests for the login helper (SOT-1386).

No real Chromium is launched: ``async_playwright`` is replaced with async fakes, so the
``open_persistent_window`` wiring and URL resolution can be exercised in any environment.
These tests are NOT marked ``e2e``/``playwright`` (no browser binary required).
"""

import pytest

import booking_monitor.sites.browser as browser_mod
from booking_monitor.login import (
    _likely_no_window_manager,
    _operability_help_text,
    _resolve_urls,
)
from booking_monitor.sites.browser import BrowserManager


class FakePage:
    def __init__(self) -> None:
        self.closed = False
        self.goto_urls: list[str] = []

    async def goto(self, url: str) -> None:
        self.goto_urls.append(url)

    async def close(self) -> None:
        self.closed = True


class FakeContext:
    def __init__(self) -> None:
        self.closed = False
        self.pages: list[FakePage] = []
        self.handlers: dict = {}

    async def new_page(self) -> FakePage:
        page = FakePage()
        self.pages.append(page)
        return page

    def on(self, event: str, cb) -> None:
        self.handlers[event] = cb

    async def close(self) -> None:
        self.closed = True


class FakeChromium:
    def __init__(self) -> None:
        self.persistent_contexts: list[FakeContext] = []

    async def launch_persistent_context(self, user_data_dir, headless=True):
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


# --- open_persistent_window ----------------------------------------------------


async def test_open_persistent_window_opens_tab_per_url_without_closing(
    fake_playwright, tmp_path
):
    mgr = BrowserManager(
        mode="persistent", headless=False, user_data_dir=str(tmp_path / "p")
    )
    urls = ["https://a.example/login", "https://b.example/login"]

    context = await mgr.open_persistent_window(urls)

    chromium = fake_playwright.chromium
    assert len(chromium.persistent_contexts) == 1
    assert context is chromium.persistent_contexts[0]
    # One tab per URL, each navigated, none closed (window stays open for login).
    assert len(context.pages) == 2
    assert [p.goto_urls[0] for p in context.pages] == urls
    assert all(not p.closed for p in context.pages)
    assert context.closed is False

    await mgr.close()
    assert context.closed


async def test_open_persistent_window_empty_opens_blank_page(fake_playwright, tmp_path):
    mgr = BrowserManager(
        mode="persistent", headless=False, user_data_dir=str(tmp_path / "p")
    )
    context = await mgr.open_persistent_window([])
    assert len(context.pages) == 1
    assert context.pages[0].goto_urls == []
    await mgr.close()


async def test_open_persistent_window_requires_persistent_mode(fake_playwright):
    mgr = BrowserManager(mode="ephemeral")
    with pytest.raises(ValueError):
        await mgr.open_persistent_window(["https://x.example"])


# --- URL resolution ------------------------------------------------------------


def test_resolve_urls_prefers_explicit_arg(monkeypatch):
    monkeypatch.setenv("BOOKING_LOGIN_URL", "https://env.example")
    assert _resolve_urls(["https://arg.example"]) == ["https://arg.example"]


def test_resolve_urls_uses_env_when_no_arg(monkeypatch):
    monkeypatch.setenv("BOOKING_LOGIN_URL", "https://a.example, https://b.example")
    assert _resolve_urls(None) == ["https://a.example", "https://b.example"]


def test_resolve_urls_deduplicates(monkeypatch):
    monkeypatch.delenv("BOOKING_LOGIN_URL", raising=False)
    assert _resolve_urls(["https://a", "https://a", "https://b"]) == [
        "https://a",
        "https://b",
    ]


# --- window-manager / operability detection ------------------------------------

_WM_ENV_VARS = (
    "DISPLAY",
    "WAYLAND_DISPLAY",
    "REMOTE_CONTAINERS_DISPLAY_SOCK",
    "XDG_CURRENT_DESKTOP",
    "DESKTOP_SESSION",
    "GNOME_DESKTOP_SESSION_ID",
)


def _clear_wm_env(monkeypatch):
    for var in _WM_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_no_wm_false_when_no_display(monkeypatch):
    _clear_wm_env(monkeypatch)
    # No DISPLAY/WAYLAND: headful won't render at all; not a "no WM" case.
    assert _likely_no_window_manager() is False


def test_no_wm_true_for_devcontainer_forwarded_display(monkeypatch):
    _clear_wm_env(monkeypatch)
    monkeypatch.setenv("DISPLAY", ":7")
    monkeypatch.setenv("REMOTE_CONTAINERS_DISPLAY_SOCK", "/tmp/.X11-unix/X7")
    assert _likely_no_window_manager() is True


def test_no_wm_true_when_display_without_desktop_markers(monkeypatch):
    _clear_wm_env(monkeypatch)
    monkeypatch.setenv("DISPLAY", ":99")
    assert _likely_no_window_manager() is True


def test_no_wm_false_on_normal_desktop(monkeypatch):
    _clear_wm_env(monkeypatch)
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "ubuntu:GNOME")
    assert _likely_no_window_manager() is False


def test_operability_help_text_mentions_display_and_fix(monkeypatch):
    monkeypatch.setenv("DISPLAY", ":7")
    text = _operability_help_text()
    assert "DISPLAY=:7" in text
    assert "fluxbox" in text
