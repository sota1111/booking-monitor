import logging
import os

from booking_monitor.services.config_loader import sample_mode_enabled

logger = logging.getLogger(__name__)


def firestore_targets_active() -> bool:
    """True when targets should be read from / written to Firestore.

    Active only outside sample-data mode (which intentionally uses local files) and
    when ``GOOGLE_CLOUD_PROJECT`` is configured. Otherwise the legacy config.json
    path is used (local development / tests), preserving backward compatibility.
    """
    if sample_mode_enabled():
        return False
    return bool(os.getenv("GOOGLE_CLOUD_PROJECT"))


def get_firestore_targets():
    """Return a ``FirestoreTargets`` instance (raises on misconfiguration)."""
    from booking_monitor.firestore_targets import FirestoreTargets

    return FirestoreTargets()
