import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

from booking_monitor.config import Notification, Target

logger = logging.getLogger(__name__)


def is_snoozed(snooze_until: Optional[str], now: Optional[datetime] = None) -> bool:
    """Return True when notifications are paused (snoozed) until a future time.

    ``snooze_until`` is an ISO 8601 timestamp (a trailing ``Z`` is accepted). Naive
    timestamps are treated as UTC. Empty, missing, or unparseable values — and any time
    already in the past — return False (notifications active).
    """
    if not snooze_until:
        return False
    raw = snooze_until.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        logger.warning("Invalid snooze_until value: %r", snooze_until)
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return dt > reference


class Notifier:
    def __init__(self, notification: Notification):
        self.notification = notification
        self._webhook_url: str = ""

    def is_snoozed(self) -> bool:
        """True when notifications are currently paused via ``snooze_until``."""
        return is_snoozed(getattr(self.notification, "snooze_until", None))

    def _get_webhook_url(self) -> str:
        if not self._webhook_url:
            env_var = self.notification.webhook_url_env or "DISCORD_WEBHOOK_URL"
            self._webhook_url = os.getenv(env_var, "")
        return self._webhook_url

    def send(self, target: Target, summary: str) -> None:
        # Snooze / pause: suppress all notifications while snoozed.
        if self.is_snoozed():
            logger.info(
                f"Notifications snoozed until {self.notification.snooze_until}; "
                f"skipping notification for {target.name}"
            )
            return

        channels = getattr(self.notification, "channels", None) or []
        if channels:
            # Multi-channel: send to every enabled channel.
            for channel in channels:
                if not channel.enabled:
                    continue
                if channel.type == "discord":
                    self._send_discord_to(channel.webhook_url_env, target, summary)
                else:
                    logger.warning(f"Unknown notification type: {channel.type}")
            return

        # Legacy single-channel path (backward compatible).
        if self.notification.type == "discord":
            self._send_discord(target, summary)
        else:
            logger.warning(f"Unknown notification type: {self.notification.type}")

    def send_session_expired(self, target: Target) -> None:
        """Notify the human that the injected session expired and needs re-export."""
        if self.notification.type == "discord":
            self._send_session_expired_discord(target)
        else:
            logger.warning(f"Unknown notification type: {self.notification.type}")

    def _send_session_expired_discord(self, target: Target) -> None:
        webhook_url = self._get_webhook_url()
        if not webhook_url:
            logger.warning(
                f"Discord webhook URL not set ({self.notification.webhook_url_env}). "
                f"Skipping session-expired notification for {target.name}."
            )
            return

        jst = timezone(timedelta(hours=9))
        now_jst = datetime.now(jst).strftime("%Y-%m-%d %H:%M")

        message = (
            f"**ログインセッションが失効しました（要対応）**\n\n"
            f"対象: {target.name}\n"
            f"URL: {target.url}\n"
            f"検出日時: {now_jst} (JST)\n\n"
            f"対象サイトに再ログインし、storage_state を再エクスポートして "
            f"Secret（`{target.session_state_env}`）を更新してください。"
            f"更新するまで、この対象の監視は認証エラーになります。"
        )

        payload = {"content": message}
        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            resp.raise_for_status()
            logger.info(f"Discord session-expired notification sent for {target.name}")
        except requests.RequestException as e:
            raise RuntimeError(f"Discord webhook request failed: {e}")

    def _build_availability_message(self, target: Target, summary: str) -> str:
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

        return message

    def _send_discord(self, target: Target, summary: str) -> None:
        webhook_url = self._get_webhook_url()
        if not webhook_url:
            logger.warning(
                f"Discord webhook URL not set ({self.notification.webhook_url_env}). "
                f"Skipping notification for {target.name}."
            )
            return

        message = self._build_availability_message(target, summary)
        payload = {"content": message}
        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            resp.raise_for_status()
            logger.info(f"Discord notification sent for {target.name}")
        except requests.RequestException as e:
            raise RuntimeError(f"Discord webhook request failed: {e}")

    def _send_discord_to(self, env_var: str, target: Target, summary: str) -> None:
        """Send a Discord availability notification to a specific channel env var."""
        webhook_url = os.getenv(env_var or "DISCORD_WEBHOOK_URL", "")
        if not webhook_url:
            logger.warning(
                f"Discord webhook URL not set ({env_var}). "
                f"Skipping notification for {target.name}."
            )
            return

        message = self._build_availability_message(target, summary)
        payload = {"content": message}
        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            resp.raise_for_status()
            logger.info(f"Discord notification sent for {target.name} via {env_var}")
        except requests.RequestException as e:
            raise RuntimeError(f"Discord webhook request failed: {e}")
