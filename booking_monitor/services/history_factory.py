import os
import logging
from booking_monitor.history import History

logger = logging.getLogger(__name__)

def get_history():
    """Returns FirestoreHistory if configured, else local History."""
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    if project:
        try:
            from booking_monitor.firestore_history import FirestoreHistory
            return FirestoreHistory()
        except Exception as e:
            logger.warning(f"Firestore unavailable, falling back to local history: {e}")
    return History()
