"""Shared base classes + helpers for Rain Bird Scheduler entities.

All entities listen for coordinator updates via HA's CoordinatorEntity
pattern and share one DeviceInfo so they group under a single device
in Settings → Devices & Services.
"""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RainBirdSchedulerCoordinator


def device_info(coordinator: RainBirdSchedulerCoordinator) -> DeviceInfo:
    """One logical device per config entry."""
    return DeviceInfo(
        identifiers={(DOMAIN, coordinator.entry.entry_id)},
        name=coordinator.entry.title,
        manufacturer="Rain Bird Scheduler",
        model=f"{len(coordinator.zones)}-zone scheduler",
        entry_type=None,
    )


class RainBirdSchedulerEntity(CoordinatorEntity[RainBirdSchedulerCoordinator]):
    """Base for all integration entities."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: RainBirdSchedulerCoordinator, role: str, name: str
    ) -> None:
        super().__init__(coordinator)
        self._role = role
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{role}"
        self._attr_name = name
        self._attr_device_info = device_info(coordinator)


class ZoneEntity(RainBirdSchedulerEntity):
    """Base for per-zone entities — adds zone-number scoping to unique_id."""

    def __init__(
        self,
        coordinator: RainBirdSchedulerCoordinator,
        zone: int,
        role: str,
        name_suffix: str,
    ) -> None:
        # Try to read a friendly name from the discovered rainbird switch so the
        # entity names match what users see in HA already (e.g. "South Yard")
        zone_switch = coordinator.zone_entity_map.get(zone)
        friendly = None
        if zone_switch:
            st = coordinator.hass.states.get(zone_switch)
            if st:
                friendly = st.attributes.get("friendly_name")
        zone_label = friendly or f"Zone {zone}"
        super().__init__(
            coordinator,
            role=f"zone_{zone}_{role}",
            name=f"{zone_label} {name_suffix}",
        )
        self._zone = zone
