import logging
import os
from datetime import datetime, timezone

import requests

from booking_monitor.config import Notification, Target

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self, notification: Notification):
        self.notification = notification
        self._webhook_url: str = ""

    def _get_webhook_url(self) -> str:
        if not self._webhook_url:
            env_var = self.notification.webhook_url_env or "DISCORD_WEBHOOK_URL"
            self._webhook_url = os.getenv(env_var, "")
        return self._webhook_url

    def send(self, target: Target, summary: str) -> None:
        if self.notification.type == "discord":
            self._send_discord(target, summary)
        else:
            logger.warning(f"Unknown notification type: {self.notification.type}")

    def _send_discord(self, target: Target, summary: str) -> None:
        webhook_url = self._get_webhook_url()
        if not webhook_url:
            raise RuntimeError(
                f"Discord webhook URL not set. "
                f"Set {self.notification.webhook_url_env} env var."
            )

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        message = (
            f"**予約枠の空きが見つかりました**\n\n"
            f"対象: {target.name}\n"
            f"検出日時: {now}\n"
            f"URL: {target.url}\n"
            f"状況: {summary}"
        )

        payload = {"content": message}
        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            resp.raise_for_status()
            logger.info(f"Discord notification sent for {target.name}")
        except requests.RequestException as e:
            raise RuntimeError(f"Discord webhook request failed: {e}")
