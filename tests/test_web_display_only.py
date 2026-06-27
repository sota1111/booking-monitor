"""SOT-1300: the Web is display-only + Firestore registration. The research
execution route (POST /run) has been removed and must no longer be reachable."""

import pytest
from fastapi.testclient import TestClient

from booking_monitor.web import create_app


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_run_route_removed(client):
    # POST /run no longer exists -> 404 (Method Not Allowed would mean it lingers).
    response = client.post("/run")
    assert response.status_code == 404


def test_display_routes_still_respond(client):
    # The login page (and the root redirect to it) keep working.
    assert client.get("/login").status_code == 200
    redirect = client.get("/", follow_redirects=False)
    assert redirect.status_code == 303
    assert redirect.headers["location"].endswith("/login")
