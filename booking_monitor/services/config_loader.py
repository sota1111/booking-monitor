import os
from booking_monitor.config import load_config

def resolve_config_path() -> str:
    """Resolves the configuration file path, falling back to example if necessary."""
    config_path = os.getenv("CONFIG_PATH", "config.json")
    if not os.path.exists(config_path) and os.path.exists("config.example.json"):
        config_path = "config.example.json"
    return config_path

def load_active_config():
    """Loads the active configuration."""
    return load_config(resolve_config_path())
