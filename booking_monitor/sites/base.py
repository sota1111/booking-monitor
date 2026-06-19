from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from booking_monitor.config import Target

if TYPE_CHECKING:
    from booking_monitor.sites.browser import BrowserManager

# A per-slot availability record: {date, time, available, source}. See
# ``booking_monitor.slots.Slot``.
SlotList = List[Dict[str, Any]]


class BaseSite(ABC):
    def __init__(self, target: Target):
        self.target = target

    @abstractmethod
    async def check(
        self, browser_manager: "Optional[BrowserManager]" = None
    ) -> Tuple[bool, str, SlotList]:
        """
        Returns (available: bool, summary: str, slots: list).

        ``slots`` is a list of per-slot availability dicts for range-based
        monitoring (SOT-833); it is empty for keyword-only checks. When
        ``browser_manager`` is provided, the check reuses the shared browser;
        otherwise it launches and tears down its own browser (backward compatible).
        Raises exception on fatal error.
        """
        ...
