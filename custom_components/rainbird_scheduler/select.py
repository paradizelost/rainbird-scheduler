"""Select entity — day-class for the eligibility schedule."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DAY_CLASSES, DOMAIN
from .coordinator import RainBirdSchedulerCoordinator
from .entity import RainBirdSchedulerEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: RainBirdSchedulerCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([DayClassSelect(coordinator)])


class DayClassSelect(RainBirdSchedulerEntity, SelectEntity):
    """Even / odd / all / day-of-week."""

    _attr_icon = "mdi:calendar-filter"
    _attr_options = DAY_CLASSES

    def __init__(self, coordinator: RainBirdSchedulerCoordinator) -> None:
        super().__init__(coordinator, "day_class", "Day Class")

    @property
    def current_option(self) -> str:
        return self.coordinator.state.day_class

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_day_class(option)
