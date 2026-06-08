import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)
HISTORY_FILE = "logs/history.jsonl"


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

    def _flush(self) -> None:
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                for entry in self._cache.values():
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"Failed to write history: {e}")
