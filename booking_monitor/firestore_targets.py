import logging
import os
from types import ModuleType

from booking_monitor.config import Target, target_from_dict, target_to_dict

firestore: ModuleType | None
try:
    from google.cloud import firestore
except ImportError:
    firestore = None

logger = logging.getLogger(__name__)


class FirestoreTargets:
    """Firestore-backed store for monitoring targets (SOT-1300).

    Targets registered from the Web (``POST /targets``) are persisted here instead
    of ``config.json`` so that the Web becomes display-only + Firestore-registration,
    and local research reads its targets from the same source of truth.

    Document id = target name (mirrors the ``monitoring_results`` convention), so
    re-adding a target with the same name updates it in place.
    """

    def __init__(self):
        if firestore is None:
            raise ImportError("google-cloud-firestore is not installed")

        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        if not project_id:
            raise ValueError("GOOGLE_CLOUD_PROJECT environment variable is not set")

        database_id = os.getenv("FIRESTORE_DATABASE_ID", "(default)")
        self.collection_name = os.getenv(
            "FIRESTORE_TARGETS_COLLECTION", "monitoring_targets"
        )

        try:
            self.db = firestore.Client(project=project_id, database=database_id)
        except Exception as e:
            logger.warning(f"Failed to initialize Firestore client: {e}")
            raise

    def list_targets(self) -> list[Target]:
        """Return all registered targets, sorted by name for a stable order."""
        try:
            docs = self.db.collection(self.collection_name).stream()
            targets = [target_from_dict(doc.to_dict()) for doc in docs]
            targets.sort(key=lambda t: t.name)
            return targets
        except Exception as e:
            logger.error(f"Error fetching targets from Firestore: {e}")
            return []

    def add_target(self, target: Target) -> None:
        """Persist a target (keyed by name) to Firestore."""
        doc_ref = self.db.collection(self.collection_name).document(target.name)
        doc_ref.set(target_to_dict(target))

    def delete_target(self, name: str) -> None:
        """Best-effort delete of a target document by name."""
        try:
            self.db.collection(self.collection_name).document(name).delete()
        except Exception as e:
            logger.error(f"Error deleting target {name} from Firestore: {e}")
