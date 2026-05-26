"""Service registration for Rain Bird Scheduler.

Services exposed (under domain `rainbird_scheduler`):
  - start_zone   { zone: int, minutes?: int }
  - start_full_cycle
  - start_test_cycle
  - stop_all

Each service dispatches to the matching coordinator. Multi-entry installs
are uncommon but supported — if more than one config entry exists, the
service runs against the first one (caller can pin via config_entry_id in
a future revision).
"""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.const import CONF_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, MAX_ZONES
from .coordinator import RainBirdSchedulerCoordinator
from .runner import (
    async_start_full_cycle,
    async_start_test_cycle,
    async_start_zone,
    async_stop_all,
)

_LOGGER = logging.getLogger(__name__)

SERVICE_START_ZONE = "start_zone"
SERVICE_START_FULL_CYCLE = "start_full_cycle"
SERVICE_START_TEST_CYCLE = "start_test_cycle"
SERVICE_STOP_ALL = "stop_all"

START_ZONE_SCHEMA = vol.Schema(
    {
        vol.Required("zone"): vol.All(int, vol.Range(min=1, max=MAX_ZONES)),
        vol.Optional("minutes"): vol.All(int, vol.Range(min=0, max=60)),
    }
)


def _first_coordinator(hass: HomeAssistant) -> RainBirdSchedulerCoordinator | None:
    entries = hass.data.get(DOMAIN, {})
    return next(iter(entries.values()), None)


def async_register_services(hass: HomeAssistant) -> None:
    """Register integration-wide services. Safe to call repeatedly."""
    if hass.services.has_service(DOMAIN, SERVICE_START_ZONE):
        return

    async def _start_zone(call: ServiceCall) -> None:
        coord = _first_coordinator(hass)
        if not coord:
            _LOGGER.warning("%s: no coordinator loaded", SERVICE_START_ZONE)
            return
        await async_start_zone(
            coord, int(call.data["zone"]), call.data.get("minutes")
        )

    async def _start_full_cycle(call: ServiceCall) -> None:
        coord = _first_coordinator(hass)
        if not coord:
            return
        await async_start_full_cycle(coord)

    async def _start_test_cycle(call: ServiceCall) -> None:
        coord = _first_coordinator(hass)
        if not coord:
            return
        await async_start_test_cycle(coord)

    async def _stop_all(call: ServiceCall) -> None:
        coord = _first_coordinator(hass)
        if not coord:
            return
        await async_stop_all(coord)

    hass.services.async_register(
        DOMAIN, SERVICE_START_ZONE, _start_zone, schema=START_ZONE_SCHEMA
    )
    hass.services.async_register(DOMAIN, SERVICE_START_FULL_CYCLE, _start_full_cycle)
    hass.services.async_register(DOMAIN, SERVICE_START_TEST_CYCLE, _start_test_cycle)
    hass.services.async_register(DOMAIN, SERVICE_STOP_ALL, _stop_all)
