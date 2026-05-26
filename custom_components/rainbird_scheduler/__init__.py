"""Rain Bird Scheduler — orchestration on top of the rainbird integration.

Provides:
  - Per-zone runtime + GPM calibration as `number` entities
  - Per-zone last-run timestamps as `datetime` entities
  - Day-class / every-Nth schedule with skip gates (rain, delay, manual, disabled)
  - Scheduled-run time listener with race-free inline verdict computation
  - Services: start_zone, start_full_cycle, start_test_cycle, stop_all
  - Synthetic activity-log sensor for clean dashboard logbook
  - Auto-generated Lovelace dashboard via strategy
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import RainBirdSchedulerCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.NUMBER,
    Platform.DATETIME,
    Platform.TIME,
    Platform.SELECT,
    Platform.SWITCH,
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Rain Bird Scheduler from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = RainBirdSchedulerCoordinator(hass, entry)
    await coordinator.async_setup()
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator: RainBirdSchedulerCoordinator | None = hass.data[DOMAIN].pop(
            entry.entry_id, None
        )
        if coordinator is not None:
            await coordinator.async_shutdown()
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
