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

def test_run_monitor_unauthorized(client):
    response = client.post("/run")
    assert response.status_code == 401

def test_run_monitor_with_api_key(client, monkeypatch):
    monkeypatch.setenv("RUN_API_KEY", "test-key")

    with patch("booking_monitor.web.monitor.run_checks") as mock_run:
        mock_run.return_value = [{"target": "test", "available": True}]

        response = client.post("/run", headers={"X-API-KEY": "test-key"})
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        mock_run.assert_called_once()

def test_session_no_body(client):
    response = client.post("/session")
    assert response.status_code == 400

@patch("firebase_admin.auth.verify_id_token")
def test_session_invalid_token(mock_verify, client):
    mock_verify.side_effect = Exception("Invalid token")
    response = client.post("/session", json={"idToken": "invalid"})
    assert response.status_code == 401
