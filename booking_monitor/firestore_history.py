import logging
import os
from datetime import datetime, timezone
from types import ModuleType
from typing import Dict, Optional

firestore: ModuleType | None
try:
    from google.cloud import firestore
except ImportError:
    firestore = None

logger = logging.getLogger(__name__)


class FirestoreHistory:
    def __init__(self):
        if firestore is None:
            raise ImportError("google-cloud-firestore is not installed")

        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        if not project_id:
            raise ValueError("GOOGLE_CLOUD_PROJECT environment variable is not set")

        database_id = os.getenv("FIRESTORE_DATABASE_ID", "(default)")
        self.collection_name = os.getenv("FIRESTORE_COLLECTION", "monitoring_results")

        try:
            self.db = firestore.Client(project=project_id, database=database_id)
        except Exception as e:
            logger.warning(f"Failed to initialize Firestore client: {e}")
            raise

    def get_last_state(self, target_name: str) -> Optional[Dict]:
        try:
            doc_ref = self.db.collection(self.collection_name).document(target_name)
            doc = doc_ref.get()
            if doc.exists:
                return doc.to_dict()
            return None
        except Exception as e:
            logger.error(f"Error fetching state from Firestore for {target_name}: {e}")
            return None

    def get_all_latest_states(self) -> list:
        """Returns all latest states from monitoring_results collection."""
        try:
            docs = self.db.collection(self.collection_name).stream()
            return [doc.to_dict() for doc in docs]
        except Exception as e:
            logger.error(f"Error fetching all states from Firestore: {e}")
            return []

    def record(
        self,
        target_name: str,
        url: str,
        available: bool,
        notified: bool,
        error: Optional[str] = None,
    ) -> None:
        try:
            doc_ref = self.db.collection(self.collection_name).document(target_name)
            entry = {
                "target_name": target_name,
                "url": url,
                "available": available,
                "notified": notified,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "error": error,
            }
            doc_ref.set(entry)
        except Exception as e:
            logger.error(f"Error recording state to Firestore for {target_name}: {e}")
            raise

    def store_check_history(
        self,
        target_name: str,
        url: str,
        available: bool,
        summary: str,
        notified: bool,
        state_changed: bool,
        error=None,
    ) -> None:
        """Appends a time-series check event to Firestore check_history collection."""
        try:
            entry = {
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "target_name": target_name,
                "url": url,
                "available": available,
                "summary": summary,
                "notified": notified,
                "state_changed": state_changed,
                "error": error,
            }
            self.db.collection("check_history").add(entry)
        except Exception as e:
            logger.error(f"Error storing check history to Firestore: {e}")

    def get_check_history(self, limit: int = 200) -> list:
        """Returns last N check history records from Firestore, newest first."""
        try:
            docs = (
                self.db.collection("check_history")
                .order_by("checked_at", direction=firestore.Query.DESCENDING)
                .limit(limit)
                .stream()
            )
            return [doc.to_dict() for doc in docs]
        except Exception as e:
            logger.error(f"Error fetching check history from Firestore: {e}")
            return []

    def store_notification_history(
        self,
        target_name: str,
        url: str,
        summary: str,
        success: bool,
        skipped: bool = False,
        error=None,
    ) -> None:
        """Appends a notification event to Firestore notification_history collection."""
        try:
            entry = {
                "sent_at": datetime.now(timezone.utc).isoformat(),
                "target_name": target_name,
                "url": url,
                "summary": summary,
                "success": success,
                "skipped": skipped,
                "error": error,
            }
            self.db.collection("notification_history").add(entry)
        except Exception as e:
            logger.error(f"Error storing notification history to Firestore: {e}")

    def get_notification_history(self, limit: int = 200) -> list:
        """Returns last N notification records from Firestore, newest first."""
        try:
            docs = (
                self.db.collection("notification_history")
                .order_by("sent_at", direction=firestore.Query.DESCENDING)
                .limit(limit)
                .stream()
            )
            return [doc.to_dict() for doc in docs]
        except Exception as e:
            logger.error(f"Error fetching notification history from Firestore: {e}")
            return []
