"""Unit tests for notification snooze and multi-channel sending (SOT-886)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from booking_monitor.config import Notification, NotificationChannel, Target
from booking_monitor.notifier import Notifier, is_snoozed


def _target():
    return Target(
        name="My Restaurant",
        url="https://example.com/reserve",
        interval_seconds=300,
        available_keywords=["空きあり"],
        unavailable_keywords=["満席"],
        notify=True,
        site_type="generic",
    )


def _ok_resp():
    class R:
        def raise_for_status(self):
            return None

    return R()


# --- is_snoozed ---------------------------------------------------------------

def test_is_snoozed_none_or_empty():
    assert is_snoozed(None) is False
    assert is_snoozed("") is False


def test_is_snoozed_future_true():
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    assert is_snoozed(future) is True


def test_is_snoozed_past_false():
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    assert is_snoozed(past) is False


def test_is_snoozed_accepts_z_suffix():
    future = datetime.now(timezone.utc) + timedelta(hours=2)
    z = future.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert is_snoozed(z) is True


def test_is_snoozed_invalid_is_false():
    assert is_snoozed("not-a-date") is False


def test_is_snoozed_naive_treated_as_utc():
    fixed_now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert is_snoozed("2026-01-01T13:00:00", now=fixed_now) is True
    assert is_snoozed("2026-01-01T11:00:00", now=fixed_now) is False


# --- send() snooze gating -----------------------------------------------------

def test_send_skips_when_snoozed(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/hook")
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    notifier = Notifier(Notification(type="discord", snooze_until=future))
    assert notifier.is_snoozed() is True
    with patch("booking_monitor.notifier.requests.post") as post:
        notifier.send(_target(), "本日空きあり")
    post.assert_not_called()


# --- multi-channel ------------------------------------------------------------

def test_send_to_each_enabled_channel(monkeypatch):
    monkeypatch.setenv("HOOK_A", "https://discord.test/a")
    monkeypatch.setenv("HOOK_B", "https://discord.test/b")
    notification = Notification(
        type="discord",
        channels=[
            NotificationChannel(type="discord", webhook_url_env="HOOK_A", enabled=True),
            NotificationChannel(type="discord", webhook_url_env="HOOK_B", enabled=True),
        ],
    )
    notifier = Notifier(notification)
    with patch(
        "booking_monitor.notifier.requests.post", return_value=_ok_resp()
    ) as post:
        notifier.send(_target(), "summary")
    assert post.call_count == 2
    urls = {c.args[0] for c in post.call_args_list}
    assert urls == {"https://discord.test/a", "https://discord.test/b"}


def test_disabled_channel_is_skipped(monkeypatch):
    monkeypatch.setenv("HOOK_A", "https://discord.test/a")
    monkeypatch.setenv("HOOK_B", "https://discord.test/b")
    notification = Notification(
        type="discord",
        channels=[
            NotificationChannel(type="discord", webhook_url_env="HOOK_A", enabled=True),
            NotificationChannel(type="discord", webhook_url_env="HOOK_B", enabled=False),
        ],
    )
    notifier = Notifier(notification)
    with patch(
        "booking_monitor.notifier.requests.post", return_value=_ok_resp()
    ) as post:
        notifier.send(_target(), "summary")
    assert post.call_count == 1
    assert post.call_args_list[0].args[0] == "https://discord.test/a"
