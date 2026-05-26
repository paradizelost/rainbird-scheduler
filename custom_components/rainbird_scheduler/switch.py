"""Switch entities for Rain Bird Scheduler toggles.

  - Schedule Enabled (master on/off for the daily run)
  - Skip Next Run (one-shot manual skip; cleared 1 min after scheduled time)
  - Show Durations (dashboard hint — toggles the duration-editor visibility)
  - Run {Weekday} (×7 — when day-class = "day of week")
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import RainBirdSchedulerCoordinator
from .entity import RainBirdSchedulerEntity
from .scheduler import WEEKDAY_NAMES

WEEKDAY_LABELS = {
    "mon": "Mondays",
    "tue": "Tuesdays",
    "wed": "Wednesdays",
    "thu": "Thursdays",
    "fri": "Fridays",
    "sat": "Saturdays",
    "sun": "Sundays",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: RainBirdSchedulerCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SwitchEntity] = [
        ScheduleEnabledSwitch(coordinator),
        SkipNextSwitch(coordinator),
        ShowDurationsSwitch(coordinator),
    ]
    for wd in WEEKDAY_NAMES:
        entities.append(WeekdaySwitch(coordinator, wd))
    async_add_entities(entities)


class ScheduleEnabledSwitch(RainBirdSchedulerEntity, SwitchEntity):
    _attr_icon = "mdi:calendar-check"

    def __init__(self, coordinator: RainBirdSchedulerCoordinator) -> None:
        super().__init__(coordinator, "schedule_enabled", "Schedule Enabled")

    @property
    def is_on(self) -> bool:
        return self.coordinator.state.schedule_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_schedule_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_schedule_enabled(False)


class SkipNextSwitch(RainBirdSchedulerEntity, SwitchEntity):
    _attr_icon = "mdi:skip-next-circle"

    def __init__(self, coordinator: RainBirdSchedulerCoordinator) -> None:
        super().__init__(coordinator, "skip_next", "Skip Next Run")

    @property
    def is_on(self) -> bool:
        return self.coordinator.state.skip_next

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_skip_next(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_skip_next(False)


class ShowDurationsSwitch(RainBirdSchedulerEntity, SwitchEntity):
    _attr_icon = "mdi:timer-cog-outline"

    def __init__(self, coordinator: RainBirdSchedulerCoordinator) -> None:
        super().__init__(coordinator, "show_durations", "Show Duration Editor")

    @property
    def is_on(self) -> bool:
        return self.coordinator.state.show_durations

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_show_durations(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_show_durations(False)


class WeekdaySwitch(RainBirdSchedulerEntity, SwitchEntity):
    _attr_icon = "mdi:calendar-week"

    def __init__(
        self, coordinator: RainBirdSchedulerCoordinator, weekday: str
    ) -> None:
        super().__init__(
            coordinator,
            f"weekday_{weekday}",
            f"Run {WEEKDAY_LABELS[weekday]}",
        )
        self._weekday = weekday

    @property
    def is_on(self) -> bool:
        return self.coordinator.state.weekdays.get(self._weekday, False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_weekday(self._weekday, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_weekday(self._weekday, False)
