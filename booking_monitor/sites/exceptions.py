"""Exceptions for site scraping, used to distinguish structural changes
(required element not found) from ordinary "no availability" results."""

from typing import Optional


class StructureChangeError(RuntimeError):
    """Raised when a required page element cannot be found after retries.

    This signals that the monitored site's structure likely changed, as opposed
    to a normal "no available slots" result. It carries enough context
    (selector, url, screenshot path) to diagnose the cause from logs alone.
    """

    def __init__(
        self,
        selector: str,
        url: Optional[str] = None,
        screenshot_path: Optional[str] = None,
    ) -> None:
        self.selector = selector
        self.url = url
        self.screenshot_path = screenshot_path
        message = (
            f"Site structure change detected: required selector not found "
            f"(selector={selector!r}, url={url!r}, screenshot={screenshot_path!r})"
        )
        super().__init__(message)
