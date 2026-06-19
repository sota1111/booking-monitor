import logging
from typing import TYPE_CHECKING, Optional, Tuple

from booking_monitor.config import Target
from booking_monitor.sites.base import SlotList
from booking_monitor.sites.registry import resolve_site

if TYPE_CHECKING:
    from booking_monitor.sites.browser import BrowserManager

logger = logging.getLogger(__name__)


async def check_target(
    target: Target, browser_manager: "Optional[BrowserManager]" = None
) -> Tuple[bool, str, SlotList]:
    """Returns (available: bool, summary: str, slots: list).

    The plugin for ``target.site_type`` is resolved from the site registry
    (see ``booking_monitor.sites.registry``). When ``browser_manager`` is
    provided, browser-based plugins reuse the shared browser; otherwise they
    launch their own (backward compatible). The generic HTTP plugin ignores
    the manager. ``slots`` carries per-slot availability for range-based
    monitoring (SOT-833) and is empty for keyword-only checks.
    """
    site = resolve_site(target)
    return await site.check(browser_manager)
