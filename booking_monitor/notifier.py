import logging
import os
from datetime import datetime, timezone, timedelta

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
        # Future: add LINE, email notification types here
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

        # JST Time
        jst = timezone(timedelta(hours=9))
        now_jst = datetime.now(jst).strftime("%Y-%m-%d %H:%M")

        message = (
            f"**予約枠の空きが見つかりました**\n\n"
            f"対象: {target.name}\n"
            f"URL: {target.url}\n"
            f"空き状況: {summary}\n"
            f"検出日時: {now_jst} (JST)\n"
            f"予約ページ: {target.url}"
        )

        if target.conditions:
            conds = target.conditions
            parts = []
            if conds.days_of_week:
                parts.append(",".join(conds.days_of_week))
            if conds.time:
                parts.append(conds.time)
            
            if parts:
                message += f"\n対象条件: {' '.join(parts)}"

        payload = {"content": message}
        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            resp.raise_for_status()
            logger.info(f"Discord notification sent for {target.name}")
        except requests.RequestException as e:
            raise RuntimeError(f"Discord webhook request failed: {e}")
