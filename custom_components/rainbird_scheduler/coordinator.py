"""Rain Bird Scheduler coordinator.

Single source of truth for schedule + per-zone state. Owns:
  - Persisted state (zone minutes/GPM/last-run, day-class, every_nth, etc.)
  - Race-free verdict computation (delegates to scheduler.py)
  - Daily scheduled-run time listener
  - Zone discovery from the loaded rainbird integration

Entities are thin proxies that read coordinator.state and call coordinator
mutators (which persist + notify listeners). The runner logic for
start_zone/full_cycle/test_cycle/stop_all lives in runner.py.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_FLUME_SENSOR,
    CONF_RAINSENSOR,
    DAY_CLASS_EVEN,
    DEFAULT_FLUME_DAILY_SENSOR,
    DOMAIN,
    MAX_ZONES,
    RAINBIRD_DOMAIN,
    VERDICT_SKIP_MANUAL,
    VERDICT_YES,
)
from .scheduler import (
    WEEKDAY_NAMES,
    ScheduleConfig,
    compute_verdict,
    decision_breakdown,
    next_fire_datetime,
    next_run_date,
    runs_in_next_30_days,
)

_LOGGER = logging.getLogger(__name__)

STORE_VERSION = 1
STORE_KEY_PREFIX = f"{DOMAIN}.state"

# How often the coordinator's normal update cycle runs. Verdict-relevant
# inputs change rarely; this cadence mostly drives "next run window" and
# similar derived sensors. Time-of-day re-renders are handled by the
# coordinator's explicit time listener, NOT by polling cadence.
UPDATE_INTERVAL = timedelta(minutes=5)

# How many days of actual-run history to retain for the dashboard calendar's
# past-month view. ~3 months covers prev/current/next month with margin.
RUN_HISTORY_DAYS = 95


@dataclass
class CoordinatorState:
    """All persisted scheduler state. Serialized to .storage via Store."""

    # Schedule shape
    day_class: str = DAY_CLASS_EVEN
    every_nth: int = 1
    cycles_per_run: int = 1
    anchor_date: date | None = None
    start_time: time = time(0, 0, 0)
    weekdays: dict[str, bool] = field(
        default_factory=lambda: {wd: True for wd in WEEKDAY_NAMES}
    )

    # Toggles
    schedule_enabled: bool = True
    skip_next: bool = False
    show_durations: bool = False

    # Rain-delay mirror (sourced from controller's number entity when present)
    rain_delay_days: int = 0

    # Run history
    last_run_at: datetime | None = None
    last_run_gallons: float = 0.0
    zone_minutes: dict[int, int] = field(default_factory=dict)
    zone_gpm: dict[int, float] = field(default_factory=dict)
    zone_last_run: dict[int, datetime | None] = field(default_factory=dict)
    # Rolling list of dates the full schedule actually ran (for the dashboard
    # calendar's past-month view). Pruned to RUN_HISTORY_DAYS.
    recent_run_dates: list[date] = field(default_factory=list)

    def schedule_config(self, wet: bool) -> ScheduleConfig:
        """Build a ScheduleConfig snapshot for verdict computation."""
        return ScheduleConfig(
            day_class=self.day_class,
            every_nth=self.every_nth,
            anchor_date=self.anchor_date,
            weekdays=dict(self.weekdays),
            enabled=self.schedule_enabled,
            skip_next=self.skip_next,
            wet=wet,
            rain_delay_days=self.rain_delay_days,
        )


def _serialize(state: CoordinatorState) -> dict[str, Any]:
    """State → JSON-safe dict for Store."""
    return {
        "day_class": state.day_class,
        "every_nth": state.every_nth,
        "cycles_per_run": state.cycles_per_run,
        "anchor_date": state.anchor_date.isoformat() if state.anchor_date else None,
        "start_time": state.start_time.isoformat(),
        "weekdays": state.weekdays,
        "schedule_enabled": state.schedule_enabled,
        "skip_next": state.skip_next,
        "show_durations": state.show_durations,
        "rain_delay_days": state.rain_delay_days,
        "last_run_at": state.last_run_at.isoformat() if state.last_run_at else None,
        "last_run_gallons": state.last_run_gallons,
        "zone_minutes": {str(k): v for k, v in state.zone_minutes.items()},
        "zone_gpm": {str(k): v for k, v in state.zone_gpm.items()},
        "zone_last_run": {
            str(k): v.isoformat() if v else None
            for k, v in state.zone_last_run.items()
        },
        "recent_run_dates": [d.isoformat() for d in state.recent_run_dates],
    }


def _deserialize(raw: dict[str, Any]) -> CoordinatorState:
    """JSON dict → CoordinatorState. Permissive about missing keys for
    forward/backward compatibility with future schema bumps."""
    state = CoordinatorState()
    if not raw:
        return state
    state.day_class = raw.get("day_class", state.day_class)
    state.every_nth = int(raw.get("every_nth", state.every_nth))
    state.cycles_per_run = int(raw.get("cycles_per_run", state.cycles_per_run))
    if raw.get("anchor_date"):
        state.anchor_date = date.fromisoformat(raw["anchor_date"])
    if raw.get("start_time"):
        state.start_time = time.fromisoformat(raw["start_time"])
    state.weekdays = {**state.weekdays, **raw.get("weekdays", {})}
    state.schedule_enabled = bool(raw.get("schedule_enabled", state.schedule_enabled))
    state.skip_next = bool(raw.get("skip_next", state.skip_next))
    state.show_durations = bool(raw.get("show_durations", state.show_durations))
    state.rain_delay_days = int(raw.get("rain_delay_days", state.rain_delay_days))
    if raw.get("last_run_at"):
        state.last_run_at = datetime.fromisoformat(raw["last_run_at"])
    state.last_run_gallons = float(raw.get("last_run_gallons", state.last_run_gallons))
    state.zone_minutes = {int(k): int(v) for k, v in raw.get("zone_minutes", {}).items()}
    state.zone_gpm = {int(k): float(v) for k, v in raw.get("zone_gpm", {}).items()}
    state.zone_last_run = {
        int(k): datetime.fromisoformat(v) if v else None
        for k, v in raw.get("zone_last_run", {}).items()
    }
    state.recent_run_dates = [
        date.fromisoformat(s) for s in raw.get("recent_run_dates", [])
    ]
    return state


class RainBirdSchedulerCoordinator(DataUpdateCoordinator[None]):
    """Coordinator that owns scheduler state + dispatches scheduled runs."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=UPDATE_INTERVAL,
        )
        self.entry = entry
        self.state = CoordinatorState()
        self._store: Store = Store(
            hass, STORE_VERSION, f"{STORE_KEY_PREFIX}.{entry.entry_id}"
        )
        self._unsub_scheduled_run = None
        self.zones: list[int] = []  # populated by _refresh_zones()
        self.zone_entity_map: dict[int, str] = {}  # zone -> switch.<id>
        self._active_cycle: asyncio.Task | None = None

    # ------------------------------------------------------------------ setup

    async def async_setup(self) -> None:
        """Initial coordinator load: persistence + zone discovery + scheduling."""
        await self._async_load_state()
        self._refresh_zones()
        await self.async_config_entry_first_refresh()
        self._schedule_next_run()

    async def async_shutdown(self) -> None:
        """Cancel timers on unload."""
        if self._unsub_scheduled_run is not None:
            self._unsub_scheduled_run()
            self._unsub_scheduled_run = None

    # ------------------------------------------------------------ persistence

    async def _async_load_state(self) -> None:
        raw = await self._store.async_load()
        self.state = _deserialize(raw or {})

        # Seed zone defaults the first time we see a zone (after discovery
        # which happens next). Done in _refresh_zones().

    async def _async_save_state(self) -> None:
        await self._store.async_save(_serialize(self.state))

    # ------------------------------------------------------------- discovery

    def _refresh_zones(self) -> None:
        """Discover zones from the loaded rainbird integration.

        Reads the entity registry for switches owned by the rainbird platform
        and groups them by their `zone` attribute. Idempotent — called on
        setup and any time we suspect zones changed.
        """
        ent_reg = er.async_get(self.hass)
        zone_map: dict[int, str] = {}
        for entry in ent_reg.entities.values():
            if entry.platform != RAINBIRD_DOMAIN or not entry.entity_id.startswith(
                "switch."
            ):
                continue
            st = self.hass.states.get(entry.entity_id)
            if not st:
                continue
            zone = st.attributes.get("zone")
            if isinstance(zone, int) and 0 < zone <= MAX_ZONES:
                zone_map[zone] = entry.entity_id

        self.zone_entity_map = zone_map
        self.zones = sorted(zone_map)

        # Seed defaults for any newly discovered zone (don't overwrite saved values)
        for z in self.zones:
            self.state.zone_minutes.setdefault(z, 0)
            self.state.zone_gpm.setdefault(z, 0.0)
            self.state.zone_last_run.setdefault(z, None)

    # ----------------------------------------------------------- input reads

    def _rainsensor_wet(self) -> bool:
        """Read configured rain-sensor binary_sensor; default to dry if not set."""
        opts = {**self.entry.data, **self.entry.options}
        eid = opts.get(CONF_RAINSENSOR)
        if not eid:
            return False
        st = self.hass.states.get(eid)
        return st is not None and st.state == "on"

    def _flume_daily_sensor(self) -> str | None:
        opts = {**self.entry.data, **self.entry.options}
        return opts.get(CONF_FLUME_SENSOR) or DEFAULT_FLUME_DAILY_SENSOR

    def _flume_daily(self) -> float:
        """Current Flume daily-total gallons, or 0 if sensor missing."""
        eid = self._flume_daily_sensor()
        if not eid:
            return 0.0
        st = self.hass.states.get(eid)
        if not st:
            return 0.0
        try:
            return float(st.state)
        except (TypeError, ValueError):
            return 0.0

    # ---------------------------------------------------------------- verdict

    def current_verdict(self, when: date | None = None) -> str:
        """Verdict for `when` (default: today in HA's local tz). Race-free —
        recomputed from current state on every call."""
        target = when or dt_util.now().date()
        config = self.state.schedule_config(wet=self._rainsensor_wet())
        return compute_verdict(target, config)

    def decision_for(self, when: date | None = None) -> dict[str, object]:
        """Full per-gate decision breakdown for `when` (default: tomorrow).

        Computed from current state with the same logic the scheduler uses to
        fire, so dashboards render the integration's real decision rather than
        re-deriving any date math. Rain/delay reflect the current snapshot (not
        an overnight forecast); the run-time re-evaluation has the final say."""
        target = when or (dt_util.now().date() + timedelta(days=1))
        config = self.state.schedule_config(wet=self._rainsensor_wet())
        data = decision_breakdown(target, config)
        data["date"] = target.isoformat()
        return data

    def total_minutes(self) -> int:
        """Sum of zone minutes × cycles_per_run."""
        zone_sum = sum(self.state.zone_minutes.get(z, 0) for z in self.zones)
        return zone_sum * max(1, self.state.cycles_per_run)

    def estimated_gallons_per_run(self) -> int:
        """Sum of zone (minutes × gpm) × cycles_per_run, rounded."""
        per = sum(
            self.state.zone_minutes.get(z, 0) * self.state.zone_gpm.get(z, 0.0)
            for z in self.zones
        )
        return round(per * max(1, self.state.cycles_per_run))

    def estimated_gallons_per_month(self) -> int:
        """Per-run × runs_in_next_30_days."""
        runs = runs_in_next_30_days(
            dt_util.now().date(), self.state.schedule_config(wet=False)
        )
        return self.estimated_gallons_per_run() * runs

    def next_eligible_date(self) -> date | None:
        return next_run_date(dt_util.now().date(), self.state.schedule_config(wet=False))

    # ---------------------------------------------------------- cycle tracking

    def set_active_cycle(self, task: asyncio.Task) -> None:
        """Track the currently-running cycle task so stop_all can cancel it."""
        self._active_cycle = task

    def clear_active_cycle(self) -> None:
        self._active_cycle = None

    def active_cycle(self) -> asyncio.Task | None:
        return self._active_cycle

    # ------------------------------------------------------ activity-log lookup

    def activity_log_entity_id(self) -> str | None:
        """Resolve the activity-log sensor's entity_id via the entity registry."""
        ent_reg = er.async_get(self.hass)
        return ent_reg.async_get_entity_id(
            "sensor", DOMAIN, f"{self.entry.entry_id}_activity_log"
        )

    # ---------------------------------------------------------------- mutators

    async def _async_after_mutation(self) -> None:
        """Persist + notify entities + (if start_time changed) reschedule."""
        await self._async_save_state()
        self.async_update_listeners()

    async def async_set_zone_minutes(self, zone: int, minutes: int) -> None:
        self.state.zone_minutes[zone] = int(minutes)
        await self._async_after_mutation()

    async def async_set_zone_gpm(self, zone: int, gpm: float) -> None:
        self.state.zone_gpm[zone] = float(gpm)
        await self._async_after_mutation()

    async def async_set_zone_last_run(self, zone: int, when: datetime | None) -> None:
        self.state.zone_last_run[zone] = when
        await self._async_after_mutation()

    async def async_set_day_class(self, day_class: str) -> None:
        self.state.day_class = day_class
        await self._async_after_mutation()

    async def async_set_every_nth(self, n: int) -> None:
        self.state.every_nth = max(1, int(n))
        await self._async_after_mutation()

    async def async_set_cycles_per_run(self, c: int) -> None:
        self.state.cycles_per_run = max(1, int(c))
        await self._async_after_mutation()

    async def async_set_anchor_date(self, d: date | None) -> None:
        self.state.anchor_date = d
        await self._async_after_mutation()

    async def async_set_start_time(self, t: time) -> None:
        self.state.start_time = t
        await self._async_after_mutation()
        self._schedule_next_run()  # re-schedule when user changes start_time

    async def async_set_weekday(self, weekday: str, enabled: bool) -> None:
        if weekday in self.state.weekdays:
            self.state.weekdays[weekday] = bool(enabled)
            await self._async_after_mutation()

    async def async_set_schedule_enabled(self, enabled: bool) -> None:
        self.state.schedule_enabled = bool(enabled)
        await self._async_after_mutation()

    async def async_set_skip_next(self, enabled: bool) -> None:
        self.state.skip_next = bool(enabled)
        await self._async_after_mutation()

    async def async_set_show_durations(self, enabled: bool) -> None:
        self.state.show_durations = bool(enabled)
        await self._async_after_mutation()

    async def async_set_rain_delay_days(self, days: int) -> None:
        self.state.rain_delay_days = max(0, int(days))
        await self._async_after_mutation()

    async def async_set_last_run(self, when: datetime, gallons: float) -> None:
        self.state.last_run_at = when
        self.state.last_run_gallons = float(gallons)
        await self._async_after_mutation()

    async def async_record_run(self, day: date) -> None:
        """Record that the full schedule ran on `day` (for the calendar's
        past-month view). Dedupes and prunes to RUN_HISTORY_DAYS."""
        cutoff = dt_util.now().date() - timedelta(days=RUN_HISTORY_DAYS)
        dates = {d for d in self.state.recent_run_dates if d >= cutoff}
        dates.add(day)
        self.state.recent_run_dates = sorted(dates)
        await self._async_after_mutation()

    # -------------------------------------------------- scheduled-run listener

    def _schedule_next_run(self) -> None:
        """Cancel any pending fire and register a fresh point-in-time listener
        for the next start_time occurrence. Called on setup and whenever
        start_time changes."""
        if self._unsub_scheduled_run is not None:
            self._unsub_scheduled_run()

        fire_at = next_fire_datetime(dt_util.now(), self.state.start_time)
        _LOGGER.debug("%s: next scheduled run at %s", self.name, fire_at.isoformat())
        self._unsub_scheduled_run = async_track_point_in_time(
            self.hass, self._async_scheduled_run_fired, fire_at
        )

    async def _async_scheduled_run_fired(self, _now) -> None:
        """Fire the scheduled-run logic and re-arm for tomorrow.

        Race-free: verdict is computed RIGHT NOW from current state, no
        cached sensor to read.
        """
        try:
            await self._async_dispatch_scheduled_run()
        finally:
            # Always re-arm for tomorrow, even if the run failed
            self._schedule_next_run()

    async def _async_dispatch_scheduled_run(self) -> None:
        """Compute today's verdict and dispatch. Always logs."""
        verdict = self.current_verdict()
        _LOGGER.info("%s: scheduled-run verdict=%s", self.name, verdict)

        # Runner module owns logbook.log + running the full cycle.
        # Imported lazily to avoid circular imports.
        from .runner import (
            async_log_scheduled_verdict,
            async_log_skip_consumed,
            async_start_full_cycle,
        )

        await async_log_scheduled_verdict(self, verdict)
        if verdict == VERDICT_YES:
            await async_start_full_cycle(self)
        elif verdict == VERDICT_SKIP_MANUAL:
            # One-shot semantics: a SKIP_MANUAL verdict means today was an
            # eligible run day (enabled + in window — the skip gate sits above
            # rain/delay) and the "Skip Next Run" toggle is what blocked it. So
            # the skip has done its job — clear it so the schedule resumes on
            # the next eligible day rather than holding indefinitely. Skipping
            # on a non-eligible day never reaches this branch, so the skip is
            # preserved until it actually consumes a run.
            await self.async_set_skip_next(False)
            await async_log_skip_consumed(self)

    # ---------------------------------------------------------------- update

    async def _async_update_data(self) -> None:
        """Coordinator's regular update tick. Recompute verdict (cheap) and
        update listeners. The verdict itself is read on-demand by sensors,
        so we just notify here."""
        # Reflect external rain delay (if a controller `number` is exposed)
        opts = {**self.entry.data, **self.entry.options}
        rain_delay_eid = opts.get("rain_delay_number")
        if rain_delay_eid:
            st = self.hass.states.get(rain_delay_eid)
            if st:
                try:
                    self.state.rain_delay_days = int(float(st.state))
                except (TypeError, ValueError):
                    pass
        return None
