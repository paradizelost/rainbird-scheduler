"""Frontend registration — serves the Lovelace strategy JS and registers it
as a Lovelace resource so HA loads it on dashboard render.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STRATEGY_URL_PATH = f"/{DOMAIN}_files/strategy.js"
LOCAL_PATH = Path(__file__).parent / "www" / "rainbird_scheduler_strategy.js"


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Serve the strategy JS + tell HA to load it as a frontend module.

    Idempotent — safe to call from each setup_entry. Skips re-registration
    if the static path is already in place.
    """
    if getattr(hass.data.setdefault(DOMAIN, {}), "_frontend_registered", False):
        return

    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                STRATEGY_URL_PATH,
                str(LOCAL_PATH),
                cache_headers=False,
            )
        ]
    )
    # Tell HA to load this URL as an extra JS module on every Lovelace render
    add_extra_js_url(hass, STRATEGY_URL_PATH)

    hass.data[DOMAIN]["_frontend_registered"] = True
    _LOGGER.info("Rain Bird Scheduler strategy JS registered at %s", STRATEGY_URL_PATH)
