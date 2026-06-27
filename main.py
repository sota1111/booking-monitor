import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv

from booking_monitor.scheduler import run_scheduler
from booking_monitor.services.config_loader import load_active_config


def setup_logging() -> None:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    os.makedirs("logs", exist_ok=True)

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    file_handler = RotatingFileHandler(
        "logs/booking_monitor.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level, logging.INFO))
    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)


def main() -> None:
    load_dotenv()
    setup_logging()

    logger = logging.getLogger(__name__)

    logger.info("Booking Monitor starting up")

    # SOT-1300: local research reads notification settings from the config file and
    # its targets from Firestore (when GOOGLE_CLOUD_PROJECT is set); otherwise it
    # falls back to the config-file targets (local / sample mode).
    try:
        config = load_active_config()
    except Exception as e:
        logger.error(f"Failed to load active config: {e}")
        sys.exit(1)

    logger.info(f"Loaded {len(config.targets)} target(s)")

    from booking_monitor.config import validate_config

    warnings = validate_config(config)
    for warning in warnings:
        logger.warning(f"Config warning: {warning}")

    run_scheduler(config)


if __name__ == "__main__":
    main()
