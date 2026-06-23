import os

from booking_monitor.config import load_config

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

def load_active_config():
    """Loads the active configuration."""
    return load_config(resolve_config_path())
