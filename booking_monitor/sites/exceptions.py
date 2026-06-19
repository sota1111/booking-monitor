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


class SessionExpiredError(RuntimeError):
    """Raised when an authenticated check lands on a login page.

    This signals that the injected ``storage_state`` session (案B: manual session
    injection) has expired and the human must re-export it, as opposed to a normal
    "no available slots" result or a structural change. It carries the target url so
    the loss-of-auth can be reported and a re-export can be requested from logs/notifications.
    """

    def __init__(self, url: Optional[str] = None) -> None:
        self.url = url
        message = (
            f"Session expired: authenticated check was redirected to a login page "
            f"(url={url!r}). Re-export the storage_state session and update the secret."
        )
        super().__init__(message)
