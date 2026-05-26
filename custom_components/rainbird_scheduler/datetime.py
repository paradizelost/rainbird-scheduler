"""DateTime entities for Rain Bird Scheduler.

  - Anchor Date — origin date for "every N days" / weekly-rotation modes
  - Last Run At — when the most-recent run finished (any source)
  - {Zone} Last Run — per-zone (runs even if cycle is single-zone)
"""

from __future__ import annotations

from datetime import date, datetime

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import RainBirdSchedulerCoordinator
from .entity import RainBirdSchedulerEntity, ZoneEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: RainBirdSchedulerCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[DateTimeEntity] = [
        AnchorDateEntity(coordinator),
        LastRunAtEntity(coordinator),
    ]
    for zone in coordinator.zones:
        entities.append(ZoneLastRunEntity(coordinator, zone))
    async_add_entities(entities)


class AnchorDateEntity(RainBirdSchedulerEntity, DateTimeEntity):
    """Anchor date for "all" + weekly-rotation modes. Time component ignored —
    HA's DateTimeEntity is the closest fit (no native DateEntity at writable
    parity), so we always set time = 00:00:00 local."""

    _attr_icon = "mdi:calendar-today"

    def __init__(self, coordinator: RainBirdSchedulerCoordinator) -> None:
        super().__init__(coordinator, "anchor_date", "Anchor Date")

    @property
    def native_value(self) -> datetime | None:
        d = self.coordinator.state.anchor_date
        if not d:
            return None
        # Return as midnight in HA's local tz so the UI shows the right date
        local_dt = datetime.combine(d, datetime.min.time())
        return dt_util.as_utc(dt_util.as_local(local_dt))

    async def async_set_value(self, value: datetime) -> None:
        await self.coordinator.async_set_anchor_date(dt_util.as_local(value).date())


class LastRunAtEntity(RainBirdSchedulerEntity, DateTimeEntity):
    """When the most-recent run finished. Set by runner; user-editable for
    manual correction."""

    _attr_icon = "mdi:history"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: RainBirdSchedulerCoordinator) -> None:
        super().__init__(coordinator, "last_run_at", "Last Run At")

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.state.last_run_at

    async def async_set_value(self, value: datetime) -> None:
        await self.coordinator.async_set_last_run(
            value, self.coordinator.state.last_run_gallons
        )


class ZoneLastRunEntity(ZoneEntity, DateTimeEntity):
    """Per-zone last-run timestamp. Persists across HA restarts (the v1.0 YAML
    workaround using switch.last_changed reset on every reboot)."""

    _attr_icon = "mdi:history"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: RainBirdSchedulerCoordinator, zone: int) -> None:
        super().__init__(coordinator, zone, "last_run", "Last Run")

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.state.zone_last_run.get(self._zone)

    async def async_set_value(self, value: datetime) -> None:
        await self.coordinator.async_set_zone_last_run(self._zone, value)
