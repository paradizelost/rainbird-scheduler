"""Frontend registration — serves the Lovelace strategy JS and registers it
as a Lovelace resource so HA loads it on dashboard render.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STRATEGY_URL_PATH = f"/{DOMAIN}_files/strategy.js"
LOCAL_PATH = Path(__file__).parent / "www" / "rainbird_scheduler_strategy.js"


def _version() -> str:
    """Integration version from manifest, used to cache-bust the strategy JS.

    The strategy is served from a fixed URL, so without a version query the
    browser / HA PWA service worker happily serves a stale copy after an update
    and the dashboard keeps running old code. Appending ?v=<version> makes each
    release a fresh URL that bypasses those caches."""
    try:
        manifest = json.loads((Path(__file__).parent / "manifest.json").read_text())
        return str(manifest.get("version", "0"))
    except Exception:  # noqa: BLE001 - never let a bad read block frontend setup
        return "0"


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Serve the strategy JS + tell HA to load it as a frontend module.

    Idempotent — safe to call from each setup_entry. Skips re-registration
    if the static path is already in place.
    """
    data = hass.data.setdefault(DOMAIN, {})
    if data.get("_frontend_registered"):
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
    # Tell HA to load this URL as an extra JS module on every Lovelace render.
    # Version query busts browser / service-worker caches on each update.
    versioned_url = f"{STRATEGY_URL_PATH}?v={_version()}"
    add_extra_js_url(hass, versioned_url)

    data["_frontend_registered"] = True
    _LOGGER.info("Rain Bird Scheduler strategy JS registered at %s", versioned_url)
