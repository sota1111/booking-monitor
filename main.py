import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv

from booking_monitor.config import load_config
from booking_monitor.scheduler import run_scheduler


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
    config_path = os.getenv("CONFIG_PATH", "config.json")

    logger.info("Booking Monitor starting up")

    try:
        config = load_config(config_path)
    except Exception as e:
        logger.error(f"Failed to load config from {config_path}: {e}")
        sys.exit(1)

    logger.info(f"Loaded {len(config.targets)} target(s)")
    run_scheduler(config)


if __name__ == "__main__":
    main()
