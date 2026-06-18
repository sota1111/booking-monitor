"""Plugin registry mapping ``site_type`` strings to site plugin classes.

Adding support for a new booking site is a two-step change:

1. Implement a ``BaseSite`` subclass in ``booking_monitor/sites/<name>.py``.
2. Register it here by adding one ``"<site_type>": <Class>`` entry to ``SITE_REGISTRY``.

The resolver falls back to :class:`GenericSite` for any unknown ``site_type`` so
that existing configs keep working (this preserves the previous default-to-generic
behavior). See ``docs/adding-a-site.md``.
"""

import logging
from typing import Dict, Type

from booking_monitor.config import Target
from booking_monitor.sites.base import BaseSite
from booking_monitor.sites.generic import GenericSite
from booking_monitor.sites.tablecheck import TableCheckSite

logger = logging.getLogger(__name__)

DEFAULT_SITE_TYPE = "generic"

# site_type -> plugin class. Add new sites here.
SITE_REGISTRY: Dict[str, Type[BaseSite]] = {
    "generic": GenericSite,
    "tablecheck": TableCheckSite,
}


def get_site_class(site_type: str) -> Type[BaseSite]:
    """Return the plugin class for ``site_type``.

    Unknown types fall back to the default (generic) plugin, logging a warning.
    """
    site_class = SITE_REGISTRY.get(site_type)
    if site_class is None:
        logger.warning(
            "Unknown site_type %r; falling back to %r plugin",
            site_type,
            DEFAULT_SITE_TYPE,
        )
        return SITE_REGISTRY[DEFAULT_SITE_TYPE]
    return site_class


def resolve_site(target: Target) -> BaseSite:
    """Instantiate the plugin for ``target.site_type``."""
    return get_site_class(target.site_type)(target)
