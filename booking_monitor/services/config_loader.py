import logging
import os

from booking_monitor.config import load_config

logger = logging.getLogger(__name__)

# Sample-data mode (SOT-1152). Truthy values enable a built-in set of sample
# targets so the dashboard can be evaluated without live scraping.
_TRUTHY = {"1", "true", "yes", "on"}
_SAMPLE_CONFIG_PATH = "config.sample.json"


def sample_mode_enabled() -> bool:
    """True when ``SEED_SAMPLE_DATA`` is set to a truthy value (case-insensitive)."""
    return os.getenv("SEED_SAMPLE_DATA", "").strip().lower() in _TRUTHY


def resolve_config_path() -> str:
    """Resolves the configuration file path, falling back to example if necessary.

    When sample-data mode is enabled (``SEED_SAMPLE_DATA``), the sample config is
    preferred (created on demand) so the dashboard shows the sample targets.
    """
    if sample_mode_enabled():
        if not os.path.exists(_SAMPLE_CONFIG_PATH):
            from booking_monitor.sample_data import write_sample_config

            write_sample_config(_SAMPLE_CONFIG_PATH)
        return _SAMPLE_CONFIG_PATH

    config_path = os.getenv("CONFIG_PATH", "config.json")
    if not os.path.exists(config_path) and os.path.exists("config.example.json"):
        config_path = "config.example.json"
    return config_path

def resolve_writable_config_path() -> str:
    """Resolves the path to write config back to when adding/editing targets.

    Never returns ``config.example.json`` (the committed example must not be
    mutated): outside sample mode this is ``CONFIG_PATH`` or ``config.json``,
    even when that file does not exist yet (it will be created on first write).
    In sample mode the sample config is the active, writable file.
    """
    if sample_mode_enabled():
        if not os.path.exists(_SAMPLE_CONFIG_PATH):
            from booking_monitor.sample_data import write_sample_config

            write_sample_config(_SAMPLE_CONFIG_PATH)
        return _SAMPLE_CONFIG_PATH
    return os.getenv("CONFIG_PATH", "config.json")


def load_active_config():
    """Loads the active configuration.

    Notification settings always come from the config file. Targets come from
    Firestore when the Firestore targets store is active (SOT-1300: Web is
    display-only + Firestore registration); otherwise the config-file targets are
    used (local / sample mode). Firestore read failures fall back to the file.
    """
    config = load_config(resolve_config_path())

    # Avoid a circular import (targets_store imports from this module).
    from booking_monitor.services.targets_store import (
        firestore_targets_active,
        get_firestore_targets,
    )

    if firestore_targets_active():
        try:
            config.targets = get_firestore_targets().list_targets()
        except Exception as e:
            logger.warning(
                "Firestore targets unavailable, using config-file targets: %s", e
            )

    return config
