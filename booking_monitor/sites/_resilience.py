"""Resilience helpers for site scraping: retrying element lookups with
exponential backoff, capturing a screenshot on failure, and raising a
structure-change error so callers can distinguish it from "no availability"."""

import asyncio
import datetime
import logging
import os
import re
from typing import Optional

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from booking_monitor.sites.exceptions import StructureChangeError

logger = logging.getLogger(__name__)

DEFAULT_SCREENSHOT_DIR = "logs/screenshots"


def _slugify(value: str) -> str:
    """Turn a CSS selector into a filesystem-safe slug."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-")
    return (slug[:60] or "selector").lower()


async def _save_screenshot(
    page, screenshot_dir: str, selector: str
) -> Optional[str]:
    """Save a full-page screenshot. Returns the path, or None on failure.

    Screenshot failures are swallowed so they never mask the original
    structure-change error.
    """
    try:
        os.makedirs(screenshot_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"structure-change_{timestamp}_{_slugify(selector)}.png"
        path = os.path.join(screenshot_dir, filename)
        await page.screenshot(path=path, full_page=True)
        return path
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Failed to capture structure-change screenshot: {e}")
        return None


async def wait_for_required_selector(
    page,
    selector: str,
    *,
    url: Optional[str] = None,
    timeout_ms: int = 10000,
    retries: int = 3,
    base_delay: float = 0.5,
    screenshot_dir: str = DEFAULT_SCREENSHOT_DIR,
):
    """Wait for a required selector, retrying with exponential backoff.

    On the final failure, capture a screenshot, log an explicit structure-change
    error, and raise :class:`StructureChangeError`. Used for elements whose
    absence means the site structure changed (not merely "no availability").
    """
    last_error: Optional[Exception] = None
    for attempt in range(retries):
        try:
            return await page.wait_for_selector(selector, timeout=timeout_ms)
        except PlaywrightTimeoutError as e:
            last_error = e
            if attempt < retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    f"Required selector not found (attempt {attempt + 1}/{retries}, "
                    f"selector={selector!r}); retrying in {delay:.1f}s"
                )
                await asyncio.sleep(delay)

    screenshot_path = await _save_screenshot(page, screenshot_dir, selector)
    logger.error(
        f"Structure change detected: required selector not found after {retries} "
        f"attempts (selector={selector!r}, url={url!r}, screenshot={screenshot_path!r})"
    )
    raise StructureChangeError(
        selector=selector, url=url, screenshot_path=screenshot_path
    ) from last_error
