"""Time entity — daily start time for the scheduled run."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import RainBirdSchedulerCoordinator
from .entity import RainBirdSchedulerEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: RainBirdSchedulerCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([StartTimeEntity(coordinator)])


class StartTimeEntity(RainBirdSchedulerEntity, TimeEntity):
    """Daily start time for the scheduled-run automation.

    Changing this triggers an immediate re-arm of the coordinator's time
    listener so the next fire reflects the new value."""

    _attr_icon = "mdi:clock-start"

    def __init__(self, coordinator: RainBirdSchedulerCoordinator) -> None:
        super().__init__(coordinator, "start_time", "Daily Start Time")

    @property
    def native_value(self) -> time:
        return self.coordinator.state.start_time

    async def async_set_value(self, value: time) -> None:
        await self.coordinator.async_set_start_time(value)
