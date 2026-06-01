"""Sensor entities for Rain Bird Scheduler.

  - Today Will Run — current verdict (yes / skip-window / skip-rain / ...)
  - Run Total Minutes — sum of zone minutes × cycles_per_run
  - Next Run Window — "HH:MM AM → HH:MM PM" range for next scheduled run
  - Run Estimated Gallons — sum of (zone minutes × gpm) × cycles
  - Monthly Estimated Gallons — per-run × runs_in_next_30_days
  - Upcoming Runs — next eligible date (with full list as attribute)
  - Activity Log — synthetic "log channel" that never changes state.
    All run-related logbook entries from this integration attribute to it,
    so the dashboard's activity card can watch only this entity and show
    exclusively explicit messages (no state-change noise, no context-chain
    expansion).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import RainBirdSchedulerCoordinator
from .entity import RainBirdSchedulerEntity
from .scheduler import runs_in_range, upcoming_runs


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: RainBirdSchedulerCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            TodayWillRunSensor(coordinator),
            RunTotalMinutesSensor(coordinator),
            NextRunWindowSensor(coordinator),
            RunEstimatedGallonsSensor(coordinator),
            MonthlyEstimatedGallonsSensor(coordinator),
            UpcomingRunsSensor(coordinator),
            ActivityLogSensor(coordinator),
        ]
    )


class TodayWillRunSensor(RainBirdSchedulerEntity, SensorEntity):
    _attr_icon = "mdi:calendar-check"

    def __init__(self, coordinator: RainBirdSchedulerCoordinator) -> None:
        super().__init__(coordinator, "today_will_run", "Today Will Run")

    @property
    def native_value(self) -> str:
        return self.coordinator.current_verdict()

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose tomorrow's full gate breakdown so the dashboard can render
        the decision matrix without re-deriving any of the logic."""
        d = self.coordinator.decision_for()  # tomorrow
        return {
            "tomorrow_date": d["date"],
            "tomorrow_verdict": d["verdict"],
            "tomorrow_enabled": d["enabled"],
            "tomorrow_in_window": d["in_window"],
            "tomorrow_skip_next": d["skip_next"],
            "tomorrow_wet": d["wet"],
            "tomorrow_rain_delay_days": d["rain_delay_days"],
        }


class RunTotalMinutesSensor(RainBirdSchedulerEntity, SensorEntity):
    _attr_icon = "mdi:timer-sand"
    _attr_native_unit_of_measurement = "min"

    def __init__(self, coordinator: RainBirdSchedulerCoordinator) -> None:
        super().__init__(coordinator, "run_total_minutes", "Run Total Minutes")

    @property
    def native_value(self) -> int:
        return self.coordinator.total_minutes()


class NextRunWindowSensor(RainBirdSchedulerEntity, SensorEntity):
    """Formatted "HH:MM AM → HH:MM PM" string for the next eligible run."""

    _attr_icon = "mdi:clock-time-four-outline"

    def __init__(self, coordinator: RainBirdSchedulerCoordinator) -> None:
        super().__init__(coordinator, "next_run_window", "Next Run Window")

    @property
    def native_value(self) -> str:
        next_date = self.coordinator.next_eligible_date()
        if next_date is None:
            return "—"
        start = datetime.combine(next_date, self.coordinator.state.start_time)
        end = start + timedelta(minutes=self.coordinator.total_minutes())
        return f"{start.strftime('%-I:%M %p')} → {end.strftime('%-I:%M %p')}"

    @property
    def extra_state_attributes(self) -> dict[str, str | int]:
        next_date = self.coordinator.next_eligible_date()
        if next_date is None:
            return {"total_minutes": self.coordinator.total_minutes()}
        start = datetime.combine(next_date, self.coordinator.state.start_time)
        end = start + timedelta(minutes=self.coordinator.total_minutes())
        return {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "total_minutes": self.coordinator.total_minutes(),
        }


class RunEstimatedGallonsSensor(RainBirdSchedulerEntity, SensorEntity):
    _attr_icon = "mdi:water"
    _attr_native_unit_of_measurement = "gal"

    def __init__(self, coordinator: RainBirdSchedulerCoordinator) -> None:
        super().__init__(
            coordinator, "run_estimated_gallons", "Run Estimated Gallons"
        )

    @property
    def native_value(self) -> int:
        return self.coordinator.estimated_gallons_per_run()


class MonthlyEstimatedGallonsSensor(RainBirdSchedulerEntity, SensorEntity):
    _attr_icon = "mdi:chart-bar"
    _attr_native_unit_of_measurement = "gal"

    def __init__(self, coordinator: RainBirdSchedulerCoordinator) -> None:
        super().__init__(
            coordinator, "monthly_estimated_gallons", "Monthly Estimated Gallons"
        )

    @property
    def native_value(self) -> int:
        return self.coordinator.estimated_gallons_per_month()

    @property
    def extra_state_attributes(self) -> dict[str, int]:
        from .scheduler import runs_in_next_30_days

        config = self.coordinator.state.schedule_config(wet=False)
        return {
            "runs_per_month": runs_in_next_30_days(dt_util.now().date(), config),
            "gallons_per_run": self.coordinator.estimated_gallons_per_run(),
        }


class UpcomingRunsSensor(RainBirdSchedulerEntity, SensorEntity):
    """State is the next eligible date as ISO.

    Attributes feed the dashboard's prev/current/next-month calendar:
      - `dates`     — upcoming scheduled-eligible days, from today through the
                      end of next month (so the future portion of all three
                      grids is fully covered).
      - `past_runs` — days the full schedule actually ran (recorded history),
                      used to mark the last-month / earlier-this-month grid.
    """

    _attr_icon = "mdi:calendar-month"

    def __init__(self, coordinator: RainBirdSchedulerCoordinator) -> None:
        super().__init__(coordinator, "upcoming_runs", "Upcoming Runs")

    @property
    def native_value(self) -> str:
        d = self.coordinator.next_eligible_date()
        return d.isoformat() if d else "none"

    @property
    def extra_state_attributes(self) -> dict[str, list[str]]:
        config = self.coordinator.state.schedule_config(wet=False)
        today = dt_util.now().date()
        # Last day of next month: jump two months forward, take the 1st, back up.
        month_after_next = today.month + 2
        y = today.year + (month_after_next - 1) // 12
        m = (month_after_next - 1) % 12 + 1
        end_next_month = date(y, m, 1) - timedelta(days=1)
        dates = runs_in_range(today, end_next_month, config)
        return {
            "dates": [d.isoformat() for d in dates],
            "past_runs": [d.isoformat() for d in self.coordinator.state.recent_run_dates],
        }


class ActivityLogSensor(RainBirdSchedulerEntity, SensorEntity):
    """Synthetic log-channel entity.

    Constant state ('log'). All `logbook.log` calls in this integration
    attribute to this entity (entity_id, domain=sensor). A dashboard logbook
    card watching ONLY this entity sees just the messages we emit — no script
    state toggles, no related state changes pulled in via context chains.

    The v1.0.0 YAML package used the same trick with a template sensor; this
    is the Python equivalent.
    """

    _attr_icon = "mdi:notebook-outline"

    def __init__(self, coordinator: RainBirdSchedulerCoordinator) -> None:
        super().__init__(coordinator, "activity_log", "Activity Log")

    @property
    def native_value(self) -> str:
        return "log"
