import logging
import os
from datetime import datetime, timezone
from typing import Dict, Optional

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
