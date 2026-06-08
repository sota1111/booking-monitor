from abc import ABC, abstractmethod
from typing import Tuple

from booking_monitor.config import Target


class BaseSite(ABC):
    def __init__(self, target: Target):
        self.target = target

    @abstractmethod
    def check(self) -> Tuple[bool, str]:
        """
        Returns (available: bool, summary: str).
        Raises exception on fatal error.
        """
        ...
