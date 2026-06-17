"""Unit tests for booking_monitor.notifier.Notifier (Discord notifications).

``requests.post`` is mocked so no network call is made.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from booking_monitor.config import Conditions, Notification, Target
from booking_monitor.notifier import Notifier


def _target(*, conditions=None):
    return Target(
        name="My Restaurant",
        url="https://example.com/reserve",
        interval_seconds=300,
        available_keywords=["空きあり"],
        unavailable_keywords=["満席"],
        notify=True,
        site_type="generic",
        conditions=conditions,
    )


def _notification(type="discord", env="DISCORD_WEBHOOK_URL"):
    return Notification(type=type, webhook_url_env=env)


def _ok_resp():
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    return resp


def test_send_discord_posts_message(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/hook")
    notifier = Notifier(_notification())
    with patch(
        "booking_monitor.notifier.requests.post", return_value=_ok_resp()
    ) as post:
        notifier.send(_target(), "本日空きあり")
    post.assert_called_once()
    content = post.call_args.kwargs["json"]["content"]
    assert "My Restaurant" in content
    assert "https://example.com/reserve" in content
    assert "本日空きあり" in content


def test_send_discord_without_webhook_url_skips(monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    notifier = Notifier(_notification())
    with patch("booking_monitor.notifier.requests.post") as post:
        notifier.send(_target(), "summary")
    post.assert_not_called()


def test_send_unknown_type_skips(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/hook")
    notifier = Notifier(_notification(type="line"))
    with patch("booking_monitor.notifier.requests.post") as post:
        notifier.send(_target(), "summary")
    post.assert_not_called()


def test_send_discord_request_error_raises_runtimeerror(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/hook")
    notifier = Notifier(_notification())
    with patch(
        "booking_monitor.notifier.requests.post",
        side_effect=requests.RequestException("boom"),
    ):
        with pytest.raises(RuntimeError) as ei:
            notifier.send(_target(), "summary")
    assert "Discord webhook request failed" in str(ei.value)


def test_send_discord_includes_conditions(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/hook")
    conditions = Conditions(days_of_week=["Saturday"], time="15:00")
    notifier = Notifier(_notification())
    with patch(
        "booking_monitor.notifier.requests.post", return_value=_ok_resp()
    ) as post:
        notifier.send(_target(conditions=conditions), "summary")
    content = post.call_args.kwargs["json"]["content"]
    assert "Saturday" in content
    assert "15:00" in content


def test_get_webhook_url_respects_custom_env(monkeypatch):
    monkeypatch.setenv("MY_HOOK", "https://discord.test/custom")
    notifier = Notifier(_notification(env="MY_HOOK"))
    assert notifier._get_webhook_url() == "https://discord.test/custom"
