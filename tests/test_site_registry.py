"""Tests for the site plugin registry (site_type -> plugin resolution)."""

from booking_monitor.config import Target
from booking_monitor.sites.generic import GenericSite
from booking_monitor.sites.registry import get_site_class, resolve_site
from booking_monitor.sites.tablecheck import TableCheckSite


def _target(site_type: str) -> Target:
    return Target(
        name="mock",
        url="https://example.com/booking",
        interval_seconds=300,
        available_keywords=["空きあり"],
        unavailable_keywords=["満席"],
        notify=False,
        site_type=site_type,
    )


def test_get_site_class_tablecheck():
    assert get_site_class("tablecheck") is TableCheckSite


def test_get_site_class_generic():
    assert get_site_class("generic") is GenericSite


def test_get_site_class_unknown_falls_back_to_generic():
    assert get_site_class("does-not-exist") is GenericSite


def test_resolve_site_returns_plugin_instance():
    site = resolve_site(_target("tablecheck"))
    assert isinstance(site, TableCheckSite)

    site = resolve_site(_target("generic"))
    assert isinstance(site, GenericSite)


def test_resolve_site_unknown_falls_back_to_generic():
    site = resolve_site(_target("unknown"))
    assert isinstance(site, GenericSite)
