from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from booking_monitor.web import create_app


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c

def test_app_creation(client):
    assert client is not None

def test_login_page(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert "Booking Monitor" in response.text

def test_root_redirect_to_login(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].endswith("/login")

class _FakeResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _FakeAsyncClient:
    """Stand-in for httpx.AsyncClient used as an async context manager."""

    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, *args, **kwargs):
        return self._resp


def _with_csrf(client):
    """Set a CSRF cookie and return the matching token for the request body."""
    token = "test-csrf-token"
    client.cookies.set("csrf_token", token)
    return token


def test_session_no_body(client):
    response = client.post("/session")
    assert response.status_code == 400


def test_session_missing_fields(client):
    token = _with_csrf(client)
    response = client.post("/session", json={"email": "", "password": "", "csrf_token": token})
    assert response.status_code == 400


def test_session_csrf_mismatch(client, monkeypatch):
    monkeypatch.setenv("FIREBASE_API_KEY", "test-key")
    client.cookies.set("csrf_token", "cookie-token")
    response = client.post(
        "/session",
        json={"email": "a@example.com", "password": "pw", "csrf_token": "body-token"},
    )
    assert response.status_code == 403


def test_session_invalid_credentials(client, monkeypatch):
    monkeypatch.setenv("FIREBASE_API_KEY", "test-key")
    token = _with_csrf(client)
    fake = _FakeAsyncClient(_FakeResp(400, {"error": {"message": "INVALID_LOGIN_CREDENTIALS"}}))
    with patch("booking_monitor.web.auth.httpx.AsyncClient", return_value=fake):
        response = client.post(
            "/session",
            json={"email": "a@example.com", "password": "wrong", "csrf_token": token},
        )
    assert response.status_code == 401


def test_session_valid_credentials(client, monkeypatch):
    monkeypatch.setenv("FIREBASE_API_KEY", "test-key")
    monkeypatch.setenv("ALLOWED_USER_EMAILS", "")
    token = _with_csrf(client)
    fake = _FakeAsyncClient(_FakeResp(200, {"email": "a@example.com"}))
    with patch("booking_monitor.web.auth.httpx.AsyncClient", return_value=fake):
        response = client.post(
            "/session",
            json={"email": "a@example.com", "password": "right", "csrf_token": token},
        )
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["email"] == "a@example.com"


def test_session_email_not_allowed(client, monkeypatch):
    monkeypatch.setenv("FIREBASE_API_KEY", "test-key")
    monkeypatch.setenv("ALLOWED_USER_EMAILS", "allowed@example.com")
    token = _with_csrf(client)
    fake = _FakeAsyncClient(_FakeResp(200, {"email": "a@example.com"}))
    with patch("booking_monitor.web.auth.httpx.AsyncClient", return_value=fake):
        response = client.post(
            "/session",
            json={"email": "a@example.com", "password": "right", "csrf_token": token},
        )
    assert response.status_code == 403
