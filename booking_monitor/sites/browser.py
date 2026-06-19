import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from playwright.async_api import Browser, Page, Playwright, async_playwright

logger = logging.getLogger(__name__)


class BrowserManager:
    """Owns one shared headless Chromium, reused across checks.

    A fresh browser context+page is created per check (isolating cookies/storage)
    and torn down in ``finally``. The browser itself is launched lazily and reused;
    if it has crashed/disconnected it is relaunched automatically.
    """

    def __init__(self, headless: bool = True) -> None:
        self._headless = headless
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None

    async def _ensure_browser(self) -> Browser:
        if self._playwright is None:
            self._playwright = await async_playwright().start()
        if self._browser is None or not self._browser.is_connected():
            if self._browser is not None:
                try:
                    await self._browser.close()
                except Exception:  # noqa: BLE001
                    pass
            self._browser = await self._playwright.chromium.launch(headless=self._headless)
            logger.info("Launched shared Chromium browser")
        return self._browser

    @asynccontextmanager
    async def new_page(
        self, storage_state: Optional[dict] = None
    ) -> AsyncIterator[Page]:
        browser = await self._ensure_browser()
        context = await browser.new_context(storage_state=storage_state)
        try:
            page = await context.new_page()
            yield page
        finally:
            await context.close()

    async def close(self) -> None:
        """Idempotent shutdown of browser + playwright."""
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
