import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

logger = logging.getLogger(__name__)

# Supported browser launch modes.
MODE_EPHEMERAL = "ephemeral"
MODE_PERSISTENT = "persistent"

DEFAULT_USER_DATA_DIR = "~/.booking-monitor/profile"


class BrowserManager:
    """Owns a Chromium instance reused across checks, in one of two modes.

    ``mode="ephemeral"`` (default, unchanged legacy behavior):
        One shared headless ``Browser`` is launched lazily and reused. A fresh
        ``new_context(storage_state=...)`` + page is created per check (isolating
        cookies/storage) and torn down in ``finally``. Login state must be supplied
        per check via an injected ``storage_state`` (案B: manual session injection).

    ``mode="persistent"`` (方式①: local logged-in profile, SOT-1141):
        One persistent browser context is launched once via
        ``chromium.launch_persistent_context(user_data_dir=...)`` and kept open for
        the whole run. Each check opens a new **page** on that persistent context and
        closes only the page (NOT the context) so the on-disk profile keeps its
        login/session across checks. The operator logs in once manually with a headful
        run (``BOOKING_HEADFUL=1``); afterwards the saved profile is reused (no
        ``storage_state`` re-export needed). ``storage_state`` is ignored in this mode
        because the profile directory already holds the session.

    In both modes ``new_page`` is an async context manager that yields a ``Page``, so
    site plugins (tablecheck/generic) are mode-agnostic and need no changes.
    """

    def __init__(
        self,
        headless: bool = True,
        mode: str = MODE_EPHEMERAL,
        user_data_dir: Optional[str] = None,
    ) -> None:
        if mode not in (MODE_EPHEMERAL, MODE_PERSISTENT):
            logger.warning(
                "Unknown browser mode %r; falling back to %r", mode, MODE_EPHEMERAL
            )
            mode = MODE_EPHEMERAL

        self._headless = headless
        self._mode = mode
        self._user_data_dir: Optional[str] = None
        if mode == MODE_PERSISTENT:
            if not user_data_dir:
                raise ValueError(
                    "persistent browser mode requires a user_data_dir "
                    "(set BOOKING_USER_DATA_DIR)"
                )
            self._user_data_dir = os.path.expanduser(user_data_dir)
            os.makedirs(self._user_data_dir, exist_ok=True)

        self._playwright: Optional[Playwright] = None
        # ephemeral mode owns a Browser; persistent mode owns a BrowserContext.
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    @property
    def mode(self) -> str:
        return self._mode

    async def _ensure_browser(self) -> Browser:
        """Ephemeral mode: launch/relaunch the shared headless browser."""
        if self._playwright is None:
            self._playwright = await async_playwright().start()
        if self._browser is None or not self._browser.is_connected():
            if self._browser is not None:
                try:
                    await self._browser.close()
                except Exception:  # noqa: BLE001
                    pass
            self._browser = await self._playwright.chromium.launch(
                headless=self._headless
            )
            logger.info("Launched shared Chromium browser")
        return self._browser

    async def _ensure_persistent_context(self) -> BrowserContext:
        """Persistent mode: launch the persistent context once and reuse it."""
        if self._playwright is None:
            self._playwright = await async_playwright().start()
        if self._context is None:
            # _user_data_dir is guaranteed set for persistent mode (validated in __init__).
            assert self._user_data_dir is not None
            self._context = await self._playwright.chromium.launch_persistent_context(
                self._user_data_dir,
                headless=self._headless,
            )
            logger.info(
                "Launched persistent Chromium context (profile: %s, headless: %s)",
                self._user_data_dir,
                self._headless,
            )
        return self._context

    @asynccontextmanager
    async def new_page(
        self, storage_state: Optional[dict] = None
    ) -> AsyncIterator[Page]:
        if self._mode == MODE_PERSISTENT:
            if storage_state is not None:
                logger.debug(
                    "storage_state is ignored in persistent mode; the profile dir "
                    "holds the session"
                )
            context = await self._ensure_persistent_context()
            page = await context.new_page()
            try:
                yield page
            finally:
                # Close only the page; keep the persistent context (session) alive.
                await page.close()
            return

        # Ephemeral mode (legacy): fresh context per check.
        browser = await self._ensure_browser()
        context = await browser.new_context(storage_state=storage_state)
        try:
            page = await context.new_page()
            yield page
        finally:
            await context.close()

    async def close(self) -> None:
        """Idempotent shutdown of whichever backend is active."""
        if self._context is not None:
            try:
                await self._context.close()
            finally:
                self._context = None
        if self._browser is not None:
            try:
                await self._browser.close()
            finally:
                self._browser = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            finally:
                self._playwright = None


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def browser_manager_from_env() -> "BrowserManager":
    """Build a :class:`BrowserManager` from ``BOOKING_*`` environment variables.

    - ``BOOKING_BROWSER_MODE``: ``ephemeral`` (default) | ``persistent``.
    - ``BOOKING_HEADFUL``: truthy → headful (``headless=False``) for the first manual
      login / debugging. Default unset → headless.
    - ``BOOKING_USER_DATA_DIR``: persistent profile dir (default
      ``~/.booking-monitor/profile``). Only used in persistent mode.
    """
    mode = os.getenv("BOOKING_BROWSER_MODE", MODE_EPHEMERAL).strip().lower()
    if mode not in (MODE_EPHEMERAL, MODE_PERSISTENT):
        logger.warning(
            "Unknown BOOKING_BROWSER_MODE=%r; falling back to %r", mode, MODE_EPHEMERAL
        )
        mode = MODE_EPHEMERAL

    headless = not _is_truthy(os.getenv("BOOKING_HEADFUL", ""))
    user_data_dir = os.getenv("BOOKING_USER_DATA_DIR", DEFAULT_USER_DATA_DIR)

    if mode == MODE_PERSISTENT:
        return BrowserManager(
            headless=headless, mode=mode, user_data_dir=user_data_dir
        )
    return BrowserManager(headless=headless, mode=mode)
