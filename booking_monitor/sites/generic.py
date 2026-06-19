import logging
from typing import TYPE_CHECKING, Optional, Tuple

import httpx

from booking_monitor.config import Target
from booking_monitor.sites.base import BaseSite, SlotList

if TYPE_CHECKING:
    from booking_monitor.sites.browser import BrowserManager

logger = logging.getLogger(__name__)


class GenericSite(BaseSite):
    """Generic HTTP + keyword check for simple sites using httpx.

    This is the default plugin used when a target's ``site_type`` does not map
    to a more specific plugin. It does not use a browser, so ``browser_manager``
    is accepted (for interface parity) but ignored.
    """

    def __init__(self, target: Target):
        super().__init__(target)

    async def check(
        self, browser_manager: "Optional[BrowserManager]" = None
    ) -> Tuple[bool, str, SlotList]:
        # Generic keyword checks have no per-slot calendar, so ``slots`` is
        # always empty (range/grid monitoring is tablecheck-only — SOT-833).
        slots: SlotList = []
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    self.target.url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (compatible; BookingMonitor/1.0)"
                    },
                )
                resp.raise_for_status()
                text = resp.text
        except Exception as e:
            raise RuntimeError(f"HTTP fetch failed: {e}")

        for kw in self.target.unavailable_keywords:
            if kw in text:
                return False, f"Found unavailable keyword: {kw}", slots

        for kw in self.target.available_keywords:
            if kw in text:
                return True, f"Found available keyword: {kw}", slots

        return False, "No matching keywords found", slots
