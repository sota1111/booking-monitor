import logging
import os

from booking_monitor.history import History

logger = logging.getLogger(__name__)

def get_history():
    """Returns FirestoreHistory if configured, else local History.

    SOT-1167: in sample-data mode the sample seeder writes only to the local
    ``logs/*.jsonl`` files. If the deployed environment (``GOOGLE_CLOUD_PROJECT``
    set) read from Firestore, the seeded sample data would never be shown on the
    dashboard. So when sample mode is enabled we always use the local ``History``,
    aligning the read backend with where the sample data is written. Sample mode is
    an evaluation mode, so this is safe and reversible (clearing the flag restores
    Firestore) and keeps sample records out of the real Firestore data.
    """
    from booking_monitor.services.config_loader import sample_mode_enabled

    if sample_mode_enabled():
        return History()

    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    if project:
        try:
            from booking_monitor.firestore_history import FirestoreHistory
            return FirestoreHistory()
        except Exception as e:
            logger.warning(f"Firestore unavailable, falling back to local history: {e}")
    return History()
