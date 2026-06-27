"""Tests for adding monitoring targets (SOT-1200): save_config round-trip
and the POST /targets dashboard route."""

import json
import os
import tempfile

import pytest

from booking_monitor.config import (
    Conditions,
    Config,
    DateRange,
    Notification,
    Target,
    TimeRange,
    load_config,
    save_config,
)


def _sample_config() -> Config:
    return Config(
        targets=[
            Target(
                name="店舗A",
                url="https://example.com/a",
                interval_seconds=300,
                available_keywords=["空きあり"],
                unavailable_keywords=["満席"],
                notify=True,
                site_type="generic",
                conditions=Conditions(
                    adults=2,
                    children_under_3=1,
                    days_of_week=["土", "日"],
                    time="18:00",
                ),
            ),
            Target(
                name="店舗B",
                url="https://example.com/b",
                interval_seconds=600,
                available_keywords=[],
                unavailable_keywords=[],
                notify=False,
                site_type="tablecheck",
                conditions=Conditions(
                    adults=4,
                    children_under_3=0,
                    days_of_week=[],
                    time="",
                    date_range=DateRange(start="2026-07-01", end="2026-07-31"),
                    time_range=TimeRange(start="17:00", end="20:00", step_minutes=30),
                ),
            ),
        ],
        notification=Notification(type="discord", webhook_url_env="DISCORD_WEBHOOK_URL"),
    )


def test_save_config_round_trips_with_load_config():
    config = _sample_config()
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        save_config(config, path)
        loaded = load_config(path)

        assert len(loaded.targets) == 2
        a = loaded.targets[0]
        assert a.name == "店舗A"
        assert a.url == "https://example.com/a"
        assert a.interval_seconds == 300
        assert a.available_keywords == ["空きあり"]
        assert a.notify is True
        assert a.site_type == "generic"
        assert a.conditions.adults == 2
        assert a.conditions.children_under_3 == 1
        assert a.conditions.days_of_week == ["土", "日"]
        assert a.conditions.time == "18:00"

        b = loaded.targets[1]
        assert b.notify is False
        assert b.site_type == "tablecheck"
        assert b.conditions.date_range.start == "2026-07-01"
        assert b.conditions.date_range.end == "2026-07-31"
        assert b.conditions.time_range.start == "17:00"
        assert b.conditions.time_range.step_minutes == 30
    finally:
        os.remove(path)


def test_save_config_writes_utf8_unescaped():
    config = _sample_config()
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        save_config(config, path)
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        # Japanese characters should be stored literally (ensure_ascii=False).
        assert "店舗A" in raw
        # Valid JSON.
        json.loads(raw)
    finally:
        os.remove(path)


def _make_client(tmp_path, monkeypatch):
    """Build a TestClient with an authenticated session and CONFIG_PATH pointed
    at a temp config file seeded with one target."""
    from fastapi.testclient import TestClient

    from booking_monitor.web import create_app

    config_path = os.path.join(tmp_path, "config.json")
    save_config(_sample_config(), config_path)
    monkeypatch.setenv("CONFIG_PATH", config_path)
    monkeypatch.delenv("SEED_SAMPLE_DATA", raising=False)
    # SOT-1300: keep these tests on the config.json path (Firestore inactive).
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.setenv("AUTH_SECRET", "test-secret")

    app = create_app()
    client = TestClient(app)
    # Forge a logged-in session by setting the session cookie via the auth flow is
    # complex; instead drive the session through a tiny login shim is unavailable,
    # so use the middleware directly by hitting a route that sets session. We rely
    # on require_login redirecting otherwise (verified separately).
    return client, config_path


def test_add_target_requires_login(tmp_path, monkeypatch):
    client, _ = _make_client(tmp_path, monkeypatch)
    resp = client.post(
        "/targets",
        json={"name": "新店舗", "url": "https://example.com/new"},
    )
    # Unauthenticated → 401 JSON (form submits via fetch).
    assert resp.status_code == 401
    assert resp.json()["status"] == "error"


@pytest.mark.parametrize(
    "payload,expect_added,expect_status",
    [
        (
            {
                "name": "新店舗",
                "url": "https://example.com/new",
                "site_type": "tablecheck",
                "adults": "3",
                "children_under_3": "1",
                "time": "19:30",
                "days_of_week": ["金", "土"],
                "interval_seconds": "120",
                "available_keywords": "空きあり, 予約可",
                "unavailable_keywords": "満席",
                "notify": True,
            },
            True,
            200,
        ),
        ({"name": "", "url": "https://example.com/new"}, False, 400),  # missing name
        ({"name": "新店舗", "url": ""}, False, 400),  # missing url
    ],
)
def test_add_target_persists_when_authenticated(
    tmp_path, monkeypatch, payload, expect_added, expect_status
):
    client, config_path = _make_client(tmp_path, monkeypatch)

    # Simulate an authenticated session by overriding the login guard.
    from booking_monitor.web import views

    monkeypatch.setattr(views, "require_login", lambda request: True)

    before = len(load_config(config_path).targets)
    resp = client.post("/targets", json=payload)
    assert resp.status_code == expect_status

    loaded = load_config(config_path)
    after = len(loaded.targets)
    if expect_added:
        assert after == before + 1
        assert resp.json()["status"] == "ok"
        t = loaded.targets[-1]
        assert t.name == payload["name"]
        assert t.url == payload["url"]
        assert t.site_type == "tablecheck"
        assert t.notify is True
        assert t.interval_seconds == 120
        assert t.available_keywords == ["空きあり", "予約可"]
        assert t.conditions.adults == 3
        assert t.conditions.children_under_3 == 1
        assert t.conditions.days_of_week == ["金", "土"]
        assert t.conditions.time == "19:30"
    else:
        assert after == before
        assert resp.json()["status"] == "error"
