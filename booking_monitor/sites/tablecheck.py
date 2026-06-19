import logging
import re
from typing import TYPE_CHECKING, List, Optional, Tuple

from booking_monitor.config import Target
from booking_monitor.sites._resilience import wait_for_required_selector
from booking_monitor.sites.base import BaseSite, SlotList
from booking_monitor.sites.exceptions import SessionExpiredError, StructureChangeError
from booking_monitor.sites.session import load_storage_state
from booking_monitor.slots import Slot, expand_slots

if TYPE_CHECKING:
    from booking_monitor.sites.browser import BrowserManager

logger = logging.getLogger(__name__)


class TableCheckSite(BaseSite):
    def __init__(self, target: Target):
        super().__init__(target)

    async def check(
        self, browser_manager: "Optional[BrowserManager]" = None
    ) -> Tuple[bool, str, SlotList]:
        storage_state = load_storage_state(self.target.session_state_env)

        if browser_manager is not None:
            async with browser_manager.new_page(storage_state=storage_state) as page:
                return await self._scrape(page)

        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(storage_state=storage_state)
            try:
                page = await context.new_page()
                return await self._scrape(page)
            finally:
                await context.close()
                await browser.close()

    async def _scrape(self, page) -> Tuple[bool, str, SlotList]:
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError

        conditions = self.target.conditions
        adults = conditions.adults if conditions else 2
        children = conditions.children_under_3 if conditions else 0
        days_of_week = conditions.days_of_week if conditions else ["Saturday", "Sunday"]
        target_time = conditions.time if conditions else "15:00"

        # Range mode (SOT-833): when a date_range + time_range is configured we
        # expand the desired (date, time) slots and report per-slot availability
        # instead of a single status.
        desired_slots = expand_slots(conditions)
        range_mode = bool(desired_slots)

        try:
            logger.info(f"Opening TableCheck URL: {self.target.url}")
            await page.goto(
                self.target.url, timeout=30000, wait_until="networkidle"
            )

            # When a session is expected (案B: injected storage_state), detect an
            # expired session: an authenticated check that gets bounced to a login
            # page (Google SSO or the site's own sign-in). Raise so it is reported
            # and a re-export can be requested, distinct from "no availability".
            if self.target.session_state_env:
                await self._raise_if_login_redirect(page)

            # Try to set adult count via dropdown
            try:
                adult_selector = (
                    "select[name*='adult'], select[id*='adult'], "
                    "[data-testid*='adult']"
                )
                if await page.locator(adult_selector).count() > 0:
                    await page.select_option(adult_selector, str(adults))
                    logger.info(f"Set adults to {adults}")
                else:
                    logger.info("Adult dropdown not found, skipping count selection")
            except Exception as e:
                logger.warning(f"Could not set adult count: {e}")

            # Try to set children count via dropdown
            try:
                child_selector = (
                    "select[name*='child'], select[id*='child'], "
                    "[data-testid*='child']"
                )
                if children > 0 and await page.locator(child_selector).count() > 0:
                    await page.select_option(child_selector, str(children))
                    logger.info(f"Set children to {children}")
            except Exception as e:
                logger.warning(f"Could not set children count: {e}")

            # Wait for the calendar (a required structural element). Retry with
            # exponential backoff; if it never appears the site structure likely
            # changed, so capture a screenshot and raise StructureChangeError.
            await wait_for_required_selector(
                page,
                "[class*='calendar'], [class*='Calendar'], table[class*='date']",
                url=self.target.url,
                timeout_ms=10000,
            )

            # Check page text for keyword-based availability
            body_element = page.locator("body")
            page_text = await body_element.inner_text()

            # Available labels from the calendar DOM (used by both paths).
            available_labels = await self._find_available_weekend_slots(
                page, days_of_week, target_time
            )

            if range_mode:
                slots = self._build_range_slots(
                    desired_slots, page_text, available_labels
                )
                any_available = any(s["available"] is True for s in slots)
                summary = self._range_summary(slots)
                return any_available, summary, slots

            # --- legacy single-status path (no range configured) ---
            for kw in self.target.unavailable_keywords:
                if kw in page_text and not any(
                    ak in page_text for ak in self.target.available_keywords
                ):
                    return False, f"Unavailable keyword found: {kw}", []

            for kw in self.target.available_keywords:
                if kw in page_text:
                    return True, f"Available keyword found: {kw}", []

            if available_labels:
                summary = f"Available slots: {', '.join(available_labels[:3])}"
                return True, summary, []

            return False, "No available slots matching conditions", []

        except (StructureChangeError, SessionExpiredError):
            # Structure change / expired session: propagate as-is (already meaningful),
            # keeping them distinct from a generic failure or "no availability".
            raise
        except PlaywrightTimeoutError as e:
            raise RuntimeError(f"Playwright timeout: {e}")
        except Exception as e:
            raise RuntimeError(f"TableCheck check failed: {e}")

    async def _raise_if_login_redirect(self, page) -> None:
        """Raise SessionExpiredError if the page landed on a login/sign-in screen."""
        current_url = (page.url or "").lower()
        login_markers = (
            "accounts.google.com",
            "/login",
            "/signin",
            "/sign_in",
            "/users/sign_in",
        )
        if any(marker in current_url for marker in login_markers):
            logger.warning(
                "Session appears expired (redirected to login URL): %s", page.url
            )
            raise SessionExpiredError(url=self.target.url)

        try:
            if await page.locator("input[type='password']").count() > 0:
                logger.warning(
                    "Session appears expired (login form detected) at %s", page.url
                )
                raise SessionExpiredError(url=self.target.url)
        except SessionExpiredError:
            raise
        except Exception as e:  # noqa: BLE001 — detection must not mask the real check
            logger.debug(f"Login-form detection skipped: {e}")

    def _build_range_slots(
        self,
        desired_slots: List[Tuple[str, str]],
        page_text: str,
        available_labels: List[str],
    ) -> SlotList:
        """Map desired (date, time) slots to availability (best-effort).

        Per-slot availability is derived from the calendar DOM labels when
        present: a slot is ``available`` when an available label mentions its
        time (and, when present, its day-of-month); otherwise it is marked
        unavailable. When no structured labels are found we fall back to the
        page-level keyword signal, and to ``unknown`` when nothing is decisive.

        NOTE: matching real TableCheck calendar slots requires live DOM
        verification (Playwright), which is unavailable in this environment, so
        the DOM mapping is heuristic and should be validated against the live
        site before relying on per-slot accuracy.
        """
        label_blob = " ".join(available_labels)
        avail_times = set(re.findall(r"\b(\d{1,2}:\d{2})\b", label_blob))

        any_unavailable_kw = any(
            kw in page_text for kw in self.target.unavailable_keywords
        )
        any_available_kw = any(
            kw in page_text for kw in self.target.available_keywords
        )

        slots: SlotList = []
        for date_str, time_str in desired_slots:
            available: Optional[bool]
            source: str
            if available_labels:
                # Time-based DOM match. Per-date disambiguation from the live
                # calendar is a follow-up requiring Playwright verification, so
                # we match on time (the robust signal) and mark non-matching
                # slots unavailable.
                matched = time_str in avail_times or time_str in label_blob
                available = bool(matched)
                source = "dom"
            elif any_available_kw and not any_unavailable_kw:
                available, source = True, "keyword"
            elif any_unavailable_kw:
                available, source = False, "keyword"
            else:
                available, source = None, "unknown"
            slots.append(
                Slot(
                    date=date_str,
                    time=time_str,
                    available=available,
                    source=source,
                ).to_dict()
            )
        return slots

    @staticmethod
    def _range_summary(slots: SlotList) -> str:
        available = [s for s in slots if s["available"] is True]
        total = len(slots)
        if not available:
            return f"範囲内に空きなし (0/{total} スロット)"
        head = ", ".join(f"{s['date']} {s['time']}" for s in available[:3])
        more = "" if len(available) <= 3 else f" 他{len(available) - 3}件"
        return f"空き {len(available)}/{total} スロット: {head}{more}"

    async def _find_available_weekend_slots(
        self, page, days_of_week: List[str], target_time: str
    ) -> List[str]:
        """Look for available slots in the calendar DOM."""
        available = []
        selectors = [
            "td:not([class*='disabled']):not([class*='full']):not([class*='closed'])"
            "[class*='available']",
            "button[class*='day']:not([disabled]):not([class*='unavailable'])",
            "[aria-label*='available']",
            "[data-available='true']",
        ]
        try:
            for selector in selectors:
                elements = await page.locator(selector).all()
                for el in elements[:10]:
                    try:
                        label = (await el.get_attribute("aria-label")) or (await el.inner_text())
                        if label:
                            available.append(label.strip())
                    except Exception:
                        pass
                if available:
                    break
        except Exception as e:
            logger.warning(f"Error finding available slots in DOM: {e}")
        return available
