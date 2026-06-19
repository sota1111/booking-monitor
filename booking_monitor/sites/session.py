"""Loading of manually-exported browser sessions (案B: manual session injection).

A human logs in to a login-required booking site (e.g. via Google SSO) in a real
browser, exports the resulting Playwright ``storage_state`` (cookies + localStorage)
as JSON, and stores it in a Secret Manager-backed environment variable. The monitor
reads that JSON here and feeds it to ``BrowserManager.new_page(storage_state=...)`` so
each check runs as the authenticated user without automating the login itself.
"""

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def load_storage_state(session_state_env: str) -> Optional[dict]:
    """Load a Playwright ``storage_state`` dict from the named environment variable.

    ``session_state_env`` is the NAME of the env var (not the value) holding the
    exported storage_state JSON. Returns ``None`` (unauthenticated, backward
    compatible) when no session is configured or the value is missing/invalid.
    Never raises — a bad/expired session should degrade gracefully, not crash the loop.
    """
    if not session_state_env:
        return None

    raw = os.getenv(session_state_env)
    if not raw:
        logger.warning(
            "session_state_env %r is set but the environment variable is empty; "
            "running unauthenticated",
            session_state_env,
        )
        return None

    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(
            "Failed to parse storage_state JSON from %r: %s; running unauthenticated",
            session_state_env,
            e,
        )
        return None
