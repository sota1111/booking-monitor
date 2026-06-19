"""Tests for storage_state session loading (案B: manual session injection)."""

import json

from booking_monitor.sites.session import load_storage_state


def test_empty_env_name_returns_none():
    assert load_storage_state("") is None


def test_missing_env_var_returns_none(monkeypatch):
    monkeypatch.delenv("BOOKING_SESSION_STATE", raising=False)
    assert load_storage_state("BOOKING_SESSION_STATE") is None


def test_empty_env_var_returns_none(monkeypatch):
    monkeypatch.setenv("BOOKING_SESSION_STATE", "")
    assert load_storage_state("BOOKING_SESSION_STATE") is None


def test_valid_json_is_parsed(monkeypatch):
    state = {"cookies": [{"name": "sid", "value": "abc"}], "origins": []}
    monkeypatch.setenv("BOOKING_SESSION_STATE", json.dumps(state))
    assert load_storage_state("BOOKING_SESSION_STATE") == state


def test_invalid_json_returns_none(monkeypatch):
    monkeypatch.setenv("BOOKING_SESSION_STATE", "{not valid json")
    assert load_storage_state("BOOKING_SESSION_STATE") is None
