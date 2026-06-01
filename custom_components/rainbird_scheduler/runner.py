"""Runner — zone-run orchestration and service handlers.

Public entry points:
  - async_log_scheduled_verdict — called by coordinator's scheduled-run dispatch
  - async_start_zone(zone, minutes=None)
  - async_start_full_cycle()
  - async_start_test_cycle()
  - async_stop_all()

These are invoked both by the coordinator's daily time-listener (full_cycle
on verdict='yes') and by services registered in services.py.

Run pattern (per zone): Flume snapshot → `rainbird.start_irrigation` →
sleep(mins) → `switch.turn_off` → 1-min settle so Flume captures trailing
flow → measure gallons → update per-zone GPM + last-run timestamp → write
logbook messages attributed to the activity-log sensor.

Cancellation: the long-running full/test-cycle tasks are tracked on the
coordinator so `stop_all` can cancel them mid-cycle; the currently-firing
zone gets a turn_off in the CancelledError handler.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util

from .const import (
    RAINBIRD_DOMAIN,
    TEST_CYCLE_MINUTES_PER_ZONE,
    VERDICT_DISABLED,
    VERDICT_SKIP_DELAY,
    VERDICT_SKIP_MANUAL,
    VERDICT_SKIP_RAIN,
    VERDICT_SKIP_WINDOW,
    VERDICT_YES,
    ZONE_SETTLE_MINUTES,
)

if TYPE_CHECKING:
    from .coordinator import RainBirdSchedulerCoordinator

_LOGGER = logging.getLogger(__name__)


# ----------------------------------------------------------------- log helper


async def _log(
    coordinator: "RainBirdSchedulerCoordinator", name: str, message: str
) -> None:
    """Write a `logbook.log` entry attributed to the activity-log sensor."""
    eid = coordinator.activity_log_entity_id()
    if not eid:
        _LOGGER.debug("activity_log entity not yet registered; skipping log")
        return
    await coordinator.hass.services.async_call(
        "logbook",
        "log",
        {"name": name, "entity_id": eid, "domain": "sensor", "message": message},
        blocking=False,
    )


def _zone_label(coordinator: "RainBirdSchedulerCoordinator", zone: int) -> str:
    """Friendly label for a zone — uses rainbird switch's friendly_name if set."""
    eid = coordinator.zone_entity_map.get(zone)
    if eid:
        st = coordinator.hass.states.get(eid)
        if st and st.attributes.get("friendly_name"):
            return st.attributes["friendly_name"]
    return f"Zone {zone}"


# ------------------------------------------------------------ scheduled-run log


async def async_log_scheduled_verdict(
    coordinator: "RainBirdSchedulerCoordinator", verdict: str
) -> None:
    """Mirror the v1.0.0 YAML automation's logbook message exactly."""
    if verdict == VERDICT_YES:
        msg = (
            f"Scheduled window — running full cycle ({coordinator.total_minutes()} min)"
        )
    elif verdict == VERDICT_SKIP_RAIN:
        msg = "Skipped — rain sensor reports wet"
    elif verdict == VERDICT_SKIP_DELAY:
        msg = (
            f"Skipped — rain delay active "
            f"({coordinator.state.rain_delay_days} days remaining)"
        )
    elif verdict == VERDICT_SKIP_MANUAL:
        msg = 'Skipped — "skip next run" toggle was on'
    elif verdict == VERDICT_SKIP_WINDOW:
        msg = (
            f"Skipped — today is not an eligible run day "
            f"({coordinator.state.day_class}, every {coordinator.state.every_nth})"
        )
    elif verdict == VERDICT_DISABLED:
        msg = "Skipped — schedule is disabled"
    else:
        msg = f'Unknown verdict: "{verdict}"'
    await _log(coordinator, "Rainbird", msg)


async def async_log_skip_consumed(
    coordinator: "RainBirdSchedulerCoordinator",
) -> None:
    """Note that the one-shot 'Skip Next Run' toggle was auto-cleared after it
    skipped an otherwise-eligible run, so the schedule resumes next time."""
    await _log(
        coordinator,
        "Rainbird",
        'Skip Next Run consumed — toggle cleared; schedule resumes next eligible day',
    )


# ----------------------------------------------------------------- run a zone


async def _run_one_zone(
    coordinator: "RainBirdSchedulerCoordinator",
    zone: int,
    minutes: int,
    *,
    label_prefix: str,
    start_suffix: str,
    finish_suffix_fn,
) -> tuple[float, float]:
    """Run a single zone end-to-end and return (gallons_used, measured_gpm).

    `start_suffix` is appended after "Zone N (Name) started · ..." in the log.
    `finish_suffix_fn(mins, gallons, gpm)` returns the finish-message tail.

    Caller owns the per-cycle aggregate accounting (start_gal, end_gal).
    """
    label = _zone_label(coordinator, zone)
    switch_eid = coordinator.zone_entity_map.get(zone)
    if not switch_eid:
        _LOGGER.warning("zone %s has no discovered switch; skipping", zone)
        return 0.0, 0.0

    zone_start_gal = coordinator._flume_daily()
    await _log(
        coordinator,
        label_prefix,
        f"Zone {zone} ({label}) started · {minutes} min planned{start_suffix}",
    )

    # Kick off the zone via the existing rainbird integration's service.
    await coordinator.hass.services.async_call(
        RAINBIRD_DOMAIN,
        "start_irrigation",
        {"entity_id": switch_eid, "duration": minutes},
        blocking=True,
    )

    try:
        await asyncio.sleep(minutes * 60)
    except asyncio.CancelledError:
        # Cancellation mid-run: turn off the switch and re-raise so the
        # cycle task unwinds cleanly.
        await coordinator.hass.services.async_call(
            "switch", "turn_off", {"entity_id": switch_eid}, blocking=False
        )
        raise

    # Normal end: explicit turn_off, then settle so Flume captures trailing flow.
    await coordinator.hass.services.async_call(
        "switch", "turn_off", {"entity_id": switch_eid}, blocking=True
    )
    await asyncio.sleep(ZONE_SETTLE_MINUTES * 60)

    zone_end_gal = coordinator._flume_daily()
    gallons_used = round(max(0.0, zone_end_gal - zone_start_gal), 1)
    measured_gpm = round(gallons_used / minutes, 1) if minutes > 0 else 0.0

    # Update per-zone calibration and last-run timestamp.
    if measured_gpm > 0:
        await coordinator.async_set_zone_gpm(zone, measured_gpm)
    await coordinator.async_set_zone_last_run(zone, dt_util.now())

    await _log(
        coordinator,
        label_prefix,
        f"Zone {zone} ({label}) finished · "
        + finish_suffix_fn(minutes, gallons_used, measured_gpm),
    )

    return gallons_used, measured_gpm


# ------------------------------------------------------------------ start_zone


async def async_start_zone(
    coordinator: "RainBirdSchedulerCoordinator",
    zone: int,
    minutes: int | None = None,
) -> None:
    """Ad-hoc single-zone run. `minutes` overrides the stored zone minutes."""
    if minutes is None:
        minutes = coordinator.state.zone_minutes.get(zone, 0)
    if minutes <= 0:
        _LOGGER.info("start_zone zone=%s minutes=0 — nothing to do", zone)
        return

    task = asyncio.create_task(_run_zone_task(coordinator, zone, minutes))
    coordinator.set_active_cycle(task)
    try:
        await task
    finally:
        coordinator.clear_active_cycle()


async def _run_zone_task(
    coordinator: "RainBirdSchedulerCoordinator", zone: int, minutes: int
) -> None:
    start_gal = coordinator._flume_daily()
    try:
        gallons_used, _ = await _run_one_zone(
            coordinator,
            zone,
            minutes,
            label_prefix="Rainbird Run Zone",
            start_suffix=" (ad-hoc)",
            finish_suffix_fn=lambda m, g, gpm: f"{m} min · {g} gal · {gpm} gpm",
        )
    finally:
        end_gal = coordinator._flume_daily()
        await coordinator.async_set_last_run(
            dt_util.now(), round(max(0.0, end_gal - start_gal), 1)
        )


# -------------------------------------------------------------- full cycle


async def async_start_full_cycle(coordinator: "RainBirdSchedulerCoordinator") -> None:
    """Run all discovered zones for their configured minutes, cycles_per_run times."""
    task = asyncio.create_task(_full_cycle_task(coordinator))
    coordinator.set_active_cycle(task)
    try:
        await task
    finally:
        coordinator.clear_active_cycle()


async def _full_cycle_task(coordinator: "RainBirdSchedulerCoordinator") -> None:
    start_gal = coordinator._flume_daily()
    # Record the run date up front so a full cycle that's cancelled mid-way
    # (partial watering) still shows on the calendar as a day that ran.
    await coordinator.async_record_run(dt_util.now().date())
    try:
        cycles = max(1, coordinator.state.cycles_per_run)
        for _cycle in range(cycles):
            for zone in coordinator.zones:
                mins = coordinator.state.zone_minutes.get(zone, 0)
                if mins <= 0:
                    continue
                await _run_one_zone(
                    coordinator,
                    zone,
                    mins,
                    label_prefix="Rainbird Full Cycle",
                    start_suffix="",
                    finish_suffix_fn=lambda m, g, gpm: f"{m} min · {g} gal · {gpm} gpm",
                )
    finally:
        end_gal = coordinator._flume_daily()
        await coordinator.async_set_last_run(
            dt_util.now(), round(max(0.0, end_gal - start_gal), 1)
        )


# -------------------------------------------------------------- test cycle


async def async_start_test_cycle(coordinator: "RainBirdSchedulerCoordinator") -> None:
    """Run every zone for 1 minute to calibrate per-zone GPM via Flume."""
    task = asyncio.create_task(_test_cycle_task(coordinator))
    coordinator.set_active_cycle(task)
    try:
        await task
    finally:
        coordinator.clear_active_cycle()


async def _test_cycle_task(coordinator: "RainBirdSchedulerCoordinator") -> None:
    start_gal = coordinator._flume_daily()
    try:
        for zone in coordinator.zones:
            await _run_one_zone(
                coordinator,
                zone,
                TEST_CYCLE_MINUTES_PER_ZONE,
                label_prefix="Rainbird Test Cycle",
                # 1-min sample by construction: gallons == gpm
                start_suffix=" calibration",
                finish_suffix_fn=lambda m, g, gpm: (
                    f"measured {gpm} gpm (1 min sample)"
                ),
            )
    finally:
        end_gal = coordinator._flume_daily()
        await coordinator.async_set_last_run(
            dt_util.now(), round(max(0.0, end_gal - start_gal), 1)
        )


# -------------------------------------------------------------- stop


async def async_stop_all(coordinator: "RainBirdSchedulerCoordinator") -> None:
    """Cancel any in-flight cycle task and turn off all rainbird zone switches."""
    task = coordinator.active_cycle()
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # Belt-and-suspenders: turn every discovered zone switch off.
    for switch_eid in coordinator.zone_entity_map.values():
        await coordinator.hass.services.async_call(
            "switch", "turn_off", {"entity_id": switch_eid}, blocking=False
        )
    await _log(coordinator, "Rainbird", "Stop All — cycle cancelled")
