"""Login helper (SOT-1386): open a headful persistent-profile browser for manual login.

The scheduler (``python main.py``) opens a page per check and closes it, so it cannot be
used to sit on a login screen. This helper opens the persistent-profile browser (方式①)
in **headful** mode, navigates to the target site(s), and keeps the window open until the
human closes it. The on-disk profile under ``BOOKING_USER_DATA_DIR`` persists the session,
so subsequent ``python main.py`` runs (headless) reuse the logged-in state.

Usage::

    BOOKING_USER_DATA_DIR=~/.booking-monitor/profile python -m booking_monitor.login
    python -m booking_monitor.login --url https://example.com/login
"""

import argparse
import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

from booking_monitor.sites.browser import (
    DEFAULT_USER_DATA_DIR,
    MODE_PERSISTENT,
    BrowserManager,
)

logger = logging.getLogger(__name__)


def _resolve_urls(urls: list[str] | None) -> list[str]:
    """Resolve target URLs: explicit arg → BOOKING_LOGIN_URL → active config targets."""
    candidates: list[str] = []
    if urls:
        candidates = list(urls)
    elif os.getenv("BOOKING_LOGIN_URL"):
        candidates = [u.strip() for u in os.environ["BOOKING_LOGIN_URL"].split(",")]
    else:
        try:
            from booking_monitor.services.config_loader import load_active_config

            config = load_active_config()
            candidates = [t.url for t in config.targets if getattr(t, "url", None)]
        except Exception as e:  # noqa: BLE001
            logger.warning("Could not load config targets for login URLs: %s", e)
            candidates = []

    # Deduplicate while preserving order; drop blanks.
    seen: set[str] = set()
    resolved: list[str] = []
    for url in candidates:
        if url and url not in seen:
            seen.add(url)
            resolved.append(url)
    return resolved


async def run_login(urls: list[str] | None = None) -> None:
    """Open a headful persistent browser at the target URL(s) and wait until closed."""
    target_urls = _resolve_urls(urls)
    user_data_dir = os.getenv("BOOKING_USER_DATA_DIR", DEFAULT_USER_DATA_DIR)

    mgr = BrowserManager(
        headless=False,
        mode=MODE_PERSISTENT,
        user_data_dir=user_data_dir,
    )

    closed = asyncio.Event()
    loop = asyncio.get_event_loop()
    try:
        context = await mgr.open_persistent_window(target_urls)

        message = (
            "\n"
            "==============================================================\n"
            " ブラウザを開きました。対象サイトにログインしてください。\n"
            f"   プロファイル: {os.path.expanduser(user_data_dir)}\n"
            + (
                "   開いたURL:\n"
                + "".join(f"     - {u}\n" for u in target_urls)
                if target_urls
                else "   (URL未指定: 空のタブを開きました)\n"
            )
            + " ログインが完了したらブラウザ窓を閉じる（または Ctrl+C）と終了します。\n"
            " セッションはプロファイルに保存され、`python main.py`(headless)で再利用されます。\n"
            "==============================================================\n"
        )
        logger.info("Login browser opened (profile: %s)", os.path.expanduser(user_data_dir))
        print(message, flush=True)

        # End when the human closes the browser window.
        def _on_close(_ctx: object) -> None:
            loop.call_soon_threadsafe(closed.set)

        context.on("close", _on_close)
        await closed.wait()
    except KeyboardInterrupt:  # Ctrl+C
        logger.info("Interrupted; closing login browser")
    finally:
        await mgr.close()


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )
    parser = argparse.ArgumentParser(
        description="Open a headful persistent browser for manual login (SOT-1386)."
    )
    parser.add_argument(
        "--url",
        action="append",
        dest="urls",
        help="URL to open for login (repeatable). Defaults to BOOKING_LOGIN_URL or "
        "the active config targets.",
    )
    args = parser.parse_args()
    try:
        asyncio.run(run_login(args.urls or None))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
