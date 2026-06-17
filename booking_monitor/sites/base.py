from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional, Tuple

from booking_monitor.config import Target

if TYPE_CHECKING:
    from booking_monitor.sites.browser import BrowserManager


class BaseSite(ABC):
    def __init__(self, target: Target):
        self.target = target

    @abstractmethod
    async def check(
        self, browser_manager: "Optional[BrowserManager]" = None
    ) -> Tuple[bool, str]:
        """
        Returns (available: bool, summary: str).

        When ``browser_manager`` is provided, the check reuses the shared browser;
        otherwise it launches and tears down its own browser (backward compatible).
        Raises exception on fatal error.
        """
        ...
