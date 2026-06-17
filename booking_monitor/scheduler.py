import asyncio
import logging
import time

from booking_monitor.checker import check_target
from booking_monitor.config import Config
from booking_monitor.history import History
from booking_monitor.notifier import Notifier
from booking_monitor.sites.browser import BrowserManager

logger = logging.getLogger(__name__)


async def _run_loop(config: Config) -> None:
    history = History()
    notifier = Notifier(config.notification)
    last_check: dict = {}
    browser_manager = BrowserManager()

    logger.info("Scheduler started")

    try:
        while True:
            now = time.time()

            for target in config.targets:
                last = last_check.get(target.name, 0)
                if now - last < target.interval_seconds:
                    continue

                last_check[target.name] = now
                logger.info(f"Checking: {target.name}")

                try:
                    available, summary = await check_target(
                        target, browser_manager=browser_manager
                    )
                    prev_state = history.get_last_state(target.name)
                    was_available = prev_state.get("available", False) if prev_state else False
                    was_notified = prev_state.get("notified", False) if prev_state else False

                    notified = False
                    if available and target.notify:
                        if not was_available or not was_notified:
                            try:
                                notifier.send(target, summary)
                                notified = True
                                logger.info(f"Notification sent for: {target.name}")
                            except Exception as e:
                                logger.error(f"Failed to send notification for {target.name}: {e}")
                        else:
                            logger.info(f"Skipping duplicate notification for: {target.name}")

                    history.record(target.name, target.url, available, notified)
                    logger.info(
                        f"Result for {target.name}: available={available}, summary={summary}"
                    )

                except Exception as e:
                    logger.error(f"Error checking {target.name}: {e}")
                    history.record(target.name, target.url, False, False, error=str(e))

            await asyncio.sleep(5)
    finally:
        await browser_manager.close()


def run_scheduler(config: Config) -> None:
    asyncio.run(_run_loop(config))
