import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)
HISTORY_FILE = "logs/history.jsonl"
CHECK_HISTORY_FILE = "logs/check_history.jsonl"
NOTIFICATION_HISTORY_FILE = "logs/notification_history.jsonl"


class History:
    def __init__(self, path: str = HISTORY_FILE):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._cache: Dict[str, Dict] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entry = json.loads(line)
                        self._cache[entry["target_name"]] = entry
        except Exception as e:
            logger.warning(f"Failed to load history: {e}")

    def get_all_latest_states(self) -> list:
        """Returns list of all cached latest states (for dashboard)."""
        return list(self._cache.values())

    def get_last_state(self, target_name: str) -> Optional[Dict]:
        return self._cache.get(target_name)

    def record(
        self,
        target_name: str,
        url: str,
        available: bool,
        notified: bool,
        error: Optional[str] = None,
    ) -> None:
        entry = {
            "target_name": target_name,
            "url": url,
            "available": available,
            "notified": notified,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "error": error,
        }
        self._cache[target_name] = entry
        self._flush()

    def store_check_history(
        self,
        target_name: str,
        url: str,
        available: bool,
        summary: str,
        notified: bool,
        state_changed: bool,
        error: Optional[str] = None,
    ) -> None:
        """Appends a time-series check event to check_history.jsonl."""
        os.makedirs(os.path.dirname(CHECK_HISTORY_FILE), exist_ok=True)
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
        try:
            with open(CHECK_HISTORY_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"Failed to write check history: {e}")

    def get_check_history(self, limit: int = 200) -> list:
        """Returns last N check history records, newest first."""
        if not os.path.exists(CHECK_HISTORY_FILE):
            return []
        try:
            with open(CHECK_HISTORY_FILE, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
            records = [json.loads(l) for l in lines]
            return list(reversed(records[-limit:]))
        except Exception as e:
            logger.warning(f"Failed to read check history: {e}")
            return []

    def store_notification_history(
        self,
        target_name: str,
        url: str,
        summary: str,
        success: bool,
        skipped: bool = False,
        error: Optional[str] = None,
    ) -> None:
        """Appends a notification event to notification_history.jsonl."""
        os.makedirs(os.path.dirname(NOTIFICATION_HISTORY_FILE), exist_ok=True)
        entry = {
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "target_name": target_name,
            "url": url,
            "summary": summary,
            "success": success,
            "skipped": skipped,
            "error": error,
        }
        try:
            with open(NOTIFICATION_HISTORY_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"Failed to write notification history: {e}")

    def get_notification_history(self, limit: int = 200) -> list:
        """Returns last N notification history records, newest first."""
        if not os.path.exists(NOTIFICATION_HISTORY_FILE):
            return []
        try:
            with open(NOTIFICATION_HISTORY_FILE, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
            records = [json.loads(l) for l in lines]
            return list(reversed(records[-limit:]))
        except Exception as e:
            logger.warning(f"Failed to read notification history: {e}")
            return []

    def _flush(self) -> None:
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                for entry in self._cache.values():
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"Failed to write history: {e}")
