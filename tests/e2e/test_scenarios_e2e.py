"""pytest-playwright scenario E2E for the admin dashboard (SOT-1264, epic SOT-1258).

Extends the smoke E2E in ``test_dashboard_e2e.py`` with user-flow scenarios that exercise
operation → navigation/display: auth guard, full nav coverage, add-target → list reflection,
notification-history tab switching, config page render, and logout. Run with ``pytest -m e2e``.

Authentication reuses the forged Starlette session cookie (signed with the test AUTH_SECRET) so
no Firebase login round-trip is needed. The add-target scenario uses the ``live_server_writable``
fixture, which points ``CONFIG_PATH`` at a throwaway temp copy so the committed
``config.example.json`` is never mutated.
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


# S1: 未認証ガード — protected pages redirect to /login with the login form shown.
@pytest.mark.parametrize("path", ["/", "/monitor", "/notification-history", "/config"])
def test_unauthenticated_pages_redirect_to_login(
    page: Page, live_server: str, path: str
) -> None:
    page.goto(f"{live_server}{path}")
    expect(page).to_have_url(re.compile(r"/login"))
    expect(page.locator("input#email")).to_be_visible()


# S2: ナビ網羅 — from the calendar top page, each nav link routes to its page and renders it.
def test_nav_links_cover_all_pages(
    page: Page, context: BrowserContext, live_server: str
) -> None:
    _authenticate(context, live_server)
    page.goto(f"{live_server}/")
    expect(page.get_by_role("heading", name="空き状況カレンダー")).to_be_visible()

    nav = page.locator("div.nav-links")

    nav.locator('a[href="/monitor"]').click()
    expect(page).to_have_url(re.compile(r"/monitor"))
    expect(page.locator("#add-target-form")).to_be_visible()

    nav.locator('a[href="/notification-history"]').click()
    expect(page).to_have_url(re.compile(r"/notification-history"))
    expect(page.locator("#panel-notify")).to_be_visible()

    nav.locator('a[href="/config"]').click()
    expect(page).to_have_url(re.compile(r"/config"))
    expect(page.get_by_role("heading", name="通知設定")).to_be_visible()

    nav.locator('a[href="/"]').click()
    expect(page).to_have_url(re.compile(r"/$"))
    expect(page.get_by_role("heading", name="空き状況カレンダー")).to_be_visible()


# S3: 監視対象追加 → 一覧反映 (writable config so the committed example is untouched).
def test_add_target_appears_in_list(
    page: Page, context: BrowserContext, live_server_writable: str
) -> None:
    _authenticate(context, live_server_writable)
    page.goto(f"{live_server_writable}/monitor")
    expect(page.locator("#add-target-form")).to_be_visible()

    unique_name = "E2Eテスト店舗-シナリオ追加"
    page.fill("#f-name", unique_name)
    page.fill("#f-url", "https://example.com/e2e-reserve")
    page.click("#add-submit")

    # The form posts JSON to /targets, shows a success note, then reloads /monitor.
    expect(page.locator("#add-result")).to_contain_text("追加しました")
    page.wait_for_url(re.compile(r"/monitor"))

    expect(page.locator("table.responsive-table")).to_contain_text(unique_name)


# S4: 履歴タブ切替 — notification panel is shown first; clicking 監視履歴 reveals the check panel.
def test_notification_history_tab_switch(
    page: Page, context: BrowserContext, live_server: str
) -> None:
    _authenticate(context, live_server)
    page.goto(f"{live_server}/notification-history")

    notify_panel = page.locator("#panel-notify")
    check_panel = page.locator("#panel-check")
    expect(notify_panel).to_be_visible()
    expect(check_panel).to_have_class(re.compile(r"\bhidden\b"))

    page.locator('button.hist-tab[data-tab="check"]').click()
    expect(check_panel).not_to_have_class(re.compile(r"\bhidden\b"))
    expect(check_panel).to_be_visible()


# S5: 設定確認ページ表示 — config page renders its sections without redirecting to /login.
def test_config_page_renders(
    page: Page, context: BrowserContext, live_server: str
) -> None:
    _authenticate(context, live_server)
    page.goto(f"{live_server}/config")
    expect(page).not_to_have_url(re.compile(r"/login"))
    expect(page.get_by_role("heading", name="通知設定")).to_be_visible()
    expect(page.get_by_role("heading", name=re.compile(r"監視対象"))).to_be_visible()


# S6: ログアウト — submitting the logout form clears the session and returns to /login.
def test_logout_redirects_to_login(
    page: Page, context: BrowserContext, live_server: str
) -> None:
    _authenticate(context, live_server)
    page.goto(f"{live_server}/")
    expect(page).not_to_have_url(re.compile(r"/login"))

    page.locator('form[action="/logout"] button[type="submit"]').click()
    expect(page).to_have_url(re.compile(r"/login"))
    expect(page.locator("input#email")).to_be_visible()
