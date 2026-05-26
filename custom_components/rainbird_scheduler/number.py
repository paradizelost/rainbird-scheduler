"""Number entities for Rain Bird Scheduler.

Per-zone:
  - {Zone} Minutes — runtime when this zone is included in a cycle
  - {Zone} GPM — calibrated flow rate (updated automatically by test/full cycle)

Singleton:
  - Every Nth Day
  - Cycles per Run
  - Rain Delay (mirrors controller's rain-delay number if present)
  - Last Run Gallons (read-only stat)
"""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, MAX_ZONES
from .coordinator import RainBirdSchedulerCoordinator
from .entity import RainBirdSchedulerEntity, ZoneEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add number entities for this config entry."""
    coordinator: RainBirdSchedulerCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[NumberEntity] = []
    for zone in coordinator.zones:
        entities.append(ZoneMinutesNumber(coordinator, zone))
        entities.append(ZoneGpmNumber(coordinator, zone))

    entities.extend(
        [
            EveryNthNumber(coordinator),
            CyclesPerRunNumber(coordinator),
            RainDelayNumber(coordinator),
            LastRunGallonsNumber(coordinator),
        ]
    )
    async_add_entities(entities)


# --------------------------------------------------------------------- per-zone


class _ZoneNumberBase(ZoneEntity, NumberEntity):
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: RainBirdSchedulerCoordinator,
        zone: int,
        role: str,
        name_suffix: str,
    ) -> None:
        super().__init__(coordinator, zone, role, name_suffix)


class ZoneMinutesNumber(_ZoneNumberBase):
    _attr_icon = "mdi:sprinkler-variant"
    _attr_native_min_value = 0
    _attr_native_max_value = 60
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "min"

    def __init__(self, coordinator: RainBirdSchedulerCoordinator, zone: int) -> None:
        super().__init__(coordinator, zone, "minutes", "Minutes")

    @property
    def native_value(self) -> int:
        return self.coordinator.state.zone_minutes.get(self._zone, 0)

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_zone_minutes(self._zone, int(value))


class ZoneGpmNumber(_ZoneNumberBase):
    _attr_icon = "mdi:water-pump"
    _attr_native_min_value = 0
    _attr_native_max_value = 50
    _attr_native_step = 0.1
    _attr_native_unit_of_measurement = "gpm"

    def __init__(self, coordinator: RainBirdSchedulerCoordinator, zone: int) -> None:
        super().__init__(coordinator, zone, "gpm", "GPM")

    @property
    def native_value(self) -> float:
        return self.coordinator.state.zone_gpm.get(self._zone, 0.0)

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_zone_gpm(self._zone, float(value))


# --------------------------------------------------------------------- singletons


class EveryNthNumber(RainBirdSchedulerEntity, NumberEntity):
    _attr_icon = "mdi:repeat-variant"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 1
    _attr_native_max_value = 14
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "windows"

    def __init__(self, coordinator: RainBirdSchedulerCoordinator) -> None:
        super().__init__(coordinator, "every_nth", "Every Nth Day")

    @property
    def native_value(self) -> int:
        return self.coordinator.state.every_nth

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_every_nth(int(value))


class CyclesPerRunNumber(RainBirdSchedulerEntity, NumberEntity):
    _attr_icon = "mdi:repeat"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 1
    _attr_native_max_value = 4
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "cycles"

    def __init__(self, coordinator: RainBirdSchedulerCoordinator) -> None:
        super().__init__(coordinator, "cycles_per_run", "Cycles per Run")

    @property
    def native_value(self) -> int:
        return self.coordinator.state.cycles_per_run

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_cycles_per_run(int(value))


class RainDelayNumber(RainBirdSchedulerEntity, NumberEntity):
    """Mirrors the Rain Bird controller's rain_delay (days). Bidirectional sync
    happens via the coordinator polling the controller number, plus this
    entity pushing changes via the rainbird service when set from the UI."""

    _attr_icon = "mdi:timer-pause-outline"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 14
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "d"

    def __init__(self, coordinator: RainBirdSchedulerCoordinator) -> None:
        super().__init__(coordinator, "rain_delay", "Rain Delay")

    @property
    def native_value(self) -> int:
        return self.coordinator.state.rain_delay_days

    async def async_set_native_value(self, value: float) -> None:
        days = int(value)
        await self.coordinator.async_set_rain_delay_days(days)
        # Also push to the controller's number entity if configured
        opts = {**self.coordinator.entry.data, **self.coordinator.entry.options}
        controller_eid = opts.get("rain_delay_number")
        if controller_eid:
            await self.hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": controller_eid, "value": days},
                blocking=False,
            )


class LastRunGallonsNumber(RainBirdSchedulerEntity, NumberEntity):
    """Read-only stat. Set by the runner after each cycle completes."""

    _attr_icon = "mdi:water"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 5000
    _attr_native_step = 0.1
    _attr_native_unit_of_measurement = "gal"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: RainBirdSchedulerCoordinator) -> None:
        super().__init__(coordinator, "last_run_gallons", "Last Run Gallons")

    @property
    def native_value(self) -> float:
        return self.coordinator.state.last_run_gallons

    async def async_set_native_value(self, value: float) -> None:
        # Allow manual correction from the UI; runner updates programmatically.
        await self.coordinator.async_set_last_run(
            self.coordinator.state.last_run_at or self.coordinator.hass.helpers.dt.utcnow(),
            float(value),
        )
