import logging
from typing import TYPE_CHECKING, List, Optional, Tuple

from booking_monitor.config import Target
from booking_monitor.sites.base import BaseSite

if TYPE_CHECKING:
    from booking_monitor.sites.browser import BrowserManager

logger = logging.getLogger(__name__)


class TableCheckSite(BaseSite):
    def __init__(self, target: Target):
        super().__init__(target)

    async def check(
        self, browser_manager: "Optional[BrowserManager]" = None
    ) -> Tuple[bool, str]:
        if browser_manager is not None:
            async with browser_manager.new_page() as page:
                return await self._scrape(page)

        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                return await self._scrape(page)
            finally:
                await browser.close()

    async def _scrape(self, page) -> Tuple[bool, str]:
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError

        conditions = self.target.conditions
        adults = conditions.adults if conditions else 2
        children = conditions.children_under_3 if conditions else 0
        days_of_week = conditions.days_of_week if conditions else ["Saturday", "Sunday"]
        target_time = conditions.time if conditions else "15:00"

        try:
            logger.info(f"Opening TableCheck URL: {self.target.url}")
            await page.goto(
                self.target.url, timeout=30000, wait_until="networkidle"
            )

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

            # Wait for calendar to render
            try:
                await page.wait_for_selector(
                    "[class*='calendar'], [class*='Calendar'], "
                    "table[class*='date']",
                    timeout=10000,
                )
            except PlaywrightTimeoutError:
                logger.warning("Calendar selector timed out, proceeding with page content")

            # Check page text for keyword-based availability
            body_element = page.locator("body")
            page_text = await body_element.inner_text()

            for kw in self.target.unavailable_keywords:
                if kw in page_text and not any(
                    ak in page_text for ak in self.target.available_keywords
                ):
                    return False, f"Unavailable keyword found: {kw}"

            for kw in self.target.available_keywords:
                if kw in page_text:
                    return True, f"Available keyword found: {kw}"

            # Try to find enabled weekend slots in calendar DOM
            available_dates = await self._find_available_weekend_slots(
                page, days_of_week, target_time
            )
            if available_dates:
                summary = f"Available slots: {', '.join(available_dates[:3])}"
                return True, summary

            return False, "No available slots matching conditions"

        except PlaywrightTimeoutError as e:
            raise RuntimeError(f"Playwright timeout: {e}")
        except Exception as e:
            raise RuntimeError(f"TableCheck check failed: {e}")

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
