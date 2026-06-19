import logging
from typing import Any, Dict, List

from booking_monitor.checker import check_target
from booking_monitor.history import History
from booking_monitor.notifier import Notifier
from booking_monitor.sites.browser import BrowserManager

logger = logging.getLogger(__name__)

async def run_checks(config: Any, history: History) -> List[Dict[str, Any]]:
    """Runs checks for all targets in the configuration and records history.

    A single shared browser is reused across all targets in this run and is
    torn down before returning.
    """
    notifier = Notifier(config.notification)
    results: List[Dict[str, Any]] = []
    browser_manager = BrowserManager()

    try:
        for target in config.targets:
            try:
                available, summary, slots = await check_target(
                    target, browser_manager=browser_manager
                )
                last_state = history.get_last_state(target.name)

                was_available = last_state.get("available", False) if last_state else False
                was_notified = last_state.get("notified", False) if last_state else False

                state_changed = available and not was_available
                notified_this_turn = False

                is_notified = was_notified
                if available:
                    if state_changed:
                        if target.notify:
                            try:
                                notifier.send(target, summary)
                                is_notified = True
                                notified_this_turn = True
                                history.store_notification_history(
                                    target_name=target.name,
                                    url=target.url,
                                    summary=summary,
                                    success=True,
                                    skipped=False,
                                )
                            except Exception as notif_err:
                                logger.error(f"Notification failed for {target.name}: {notif_err}")
                                history.store_notification_history(
                                    target_name=target.name,
                                    url=target.url,
                                    summary=summary,
                                    success=False,
                                    skipped=False,
                                    error=str(notif_err),
                                )
                        else:
                            # notify=False: availability found but notification skipped
                            history.store_notification_history(
                                target_name=target.name,
                                url=target.url,
                                summary=summary,
                                success=False,
                                skipped=True,
                            )
                else:
                    is_notified = False

                history.record(
                    target.name, target.url, available, is_notified, slots=slots
                )
                history.store_check_history(
                    target_name=target.name,
                    url=target.url,
                    available=available,
                    summary=summary,
                    notified=notified_this_turn,
                    state_changed=state_changed,
                    slots=slots,
                )

                results.append({
                    "target": target.name,
                    "available": available,
                    "summary": summary,
                    "notified": notified_this_turn or (available and was_notified),
                    "state_changed": state_changed,
                    "slots": slots,
                })
            except Exception as e:
                logger.error(f"Error checking target {target.name}: {e}")
                history.record(target.name, target.url, False, False, error=str(e))
                history.store_check_history(
                    target_name=target.name,
                    url=target.url,
                    available=False,
                    summary="",
                    notified=False,
                    state_changed=False,
                    error=str(e),
                )
                results.append({
                    "target": target.name,
                    "available": False,
                    "summary": f"Error: {str(e)}",
                    "notified": False,
                    "state_changed": False
                })
    finally:
        await browser_manager.close()

    return results
