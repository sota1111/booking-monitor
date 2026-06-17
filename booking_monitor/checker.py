import logging
from typing import Tuple

import httpx

from booking_monitor.config import Target

logger = logging.getLogger(__name__)


async def check_target(target: Target) -> Tuple[bool, str]:
    """Returns (available: bool, summary: str)."""
    if target.site_type == "tablecheck":
        from booking_monitor.sites.tablecheck import TableCheckSite
        site = TableCheckSite(target)
        return await site.check()
    else:
        return await _check_generic(target)


async def _check_generic(target: Target) -> Tuple[bool, str]:
    """Generic HTTP + keyword check for simple sites using httpx."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                target.url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; BookingMonitor/1.0)"},
            )
            resp.raise_for_status()
            text = resp.text
    except Exception as e:
        raise RuntimeError(f"HTTP fetch failed: {e}")

    for kw in target.unavailable_keywords:
        if kw in text:
            return False, f"Found unavailable keyword: {kw}"

    for kw in target.available_keywords:
        if kw in text:
            return True, f"Found available keyword: {kw}"

    return False, "No matching keywords found"
