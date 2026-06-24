"""pytest-playwright smoke E2E for the admin dashboard (SOT-1154).

Drives the live admin UI via a real browser. Run with `pytest -m e2e`. Authentication uses
a forged Starlette session cookie (signed with the test AUTH_SECRET) so no Firebase login
round-trip is needed.
"""

from __future__ import annotations

import base64
import json
import re

import itsdangerous
import pytest
from playwright.sync_api import BrowserContext, Page, expect

from tests.e2e.conftest import E2E_AUTH_SECRET

pytestmark = pytest.mark.e2e


def _session_cookie(user: str = "test@example.com") -> str:
    # Starlette SessionMiddleware: signer.sign(b64encode(json.dumps(session))).
    signer = itsdangerous.TimestampSigner(E2E_AUTH_SECRET)
    data = base64.b64encode(json.dumps({"user": user}).encode())
    return signer.sign(data).decode()


def _authenticate(context: BrowserContext, base_url: str) -> None:
    context.add_cookies([{"name": "session", "value": _session_cookie(), "url": base_url}])


def test_unauthenticated_root_redirects_to_login(page: Page, live_server: str) -> None:
    page.goto(f"{live_server}/")
    expect(page).to_have_url(re.compile(r"/login"))
    expect(page.locator("input#email")).to_be_visible()


def test_login_page_renders_form(page: Page, live_server: str) -> None:
    page.goto(f"{live_server}/login")
    expect(page.locator("input#email")).to_be_visible()
    expect(page.locator("input#password")).to_be_visible()
    expect(page.locator("button#submitBtn")).to_be_visible()


def test_authenticated_status_page_renders(
    page: Page, context: BrowserContext, live_server: str
) -> None:
    _authenticate(context, live_server)
    page.goto(f"{live_server}/")
    expect(page).not_to_have_url(re.compile(r"/login"))
    expect(page.locator("span.brand")).to_contain_text("Booking Monitor")
    expect(page.locator("div.nav-links")).to_be_visible()


def test_authenticated_config_page_renders(
    page: Page, context: BrowserContext, live_server: str
) -> None:
    _authenticate(context, live_server)
    page.goto(f"{live_server}/config")
    expect(page).not_to_have_url(re.compile(r"/login"))
