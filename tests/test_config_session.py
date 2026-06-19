"""Tests for the session_state_env config field loading."""

import json
import os
import tempfile

from booking_monitor.config import load_config


def _write_config(data: dict) -> str:
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return path


def test_session_state_env_loaded_when_present():
    path = _write_config(
        {
            "targets": [
                {
                    "name": "shop",
                    "url": "https://example.com/reserve",
                    "interval_seconds": 300,
                    "available_keywords": ["空きあり"],
                    "unavailable_keywords": ["満席"],
                    "notify": True,
                    "site_type": "tablecheck",
                    "session_state_env": "BOOKING_SESSION_STATE",
                }
            ],
            "notification": {"type": "discord"},
        }
    )
    try:
        config = load_config(path)
        assert config.targets[0].session_state_env == "BOOKING_SESSION_STATE"
    finally:
        os.remove(path)


def test_session_state_env_defaults_to_empty():
    path = _write_config(
        {
            "targets": [
                {
                    "name": "shop",
                    "url": "https://example.com/reserve",
                    "interval_seconds": 300,
                    "available_keywords": ["空きあり"],
                    "unavailable_keywords": ["満席"],
                    "notify": True,
                }
            ],
            "notification": {"type": "discord"},
        }
    )
    try:
        config = load_config(path)
        assert config.targets[0].session_state_env == ""
    finally:
        os.remove(path)
