"""Runner: zone-run orchestration (start_zone, full_cycle, test_cycle, stop_all).

Stub — implementation lands in task #26. Functions here are called by the
coordinator's scheduled-run dispatcher and by service handlers.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .coordinator import RainBirdSchedulerCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_log_scheduled_verdict(
    coordinator: "RainBirdSchedulerCoordinator", verdict: str
) -> None:
    """Write a logbook entry for today's scheduled-run verdict.

    Will be implemented in task #26 to write to the activity-log sensor with
    a human-readable message matching the v1.0.0 YAML package wording.
    """
    _LOGGER.info("[stub] scheduled verdict: %s", verdict)


async def async_start_zone(
    coordinator: "RainBirdSchedulerCoordinator",
    zone: int,
    minutes: int | None = None,
) -> None:
    """Run a single zone, with optional minutes override.

    Will Flume-snapshot before, start_irrigation via rainbird service, wait,
    turn off, settle delay, measure, update GPM + last_run, emit log entries.
    """
    _LOGGER.info("[stub] start_zone zone=%s minutes=%s", zone, minutes)


async def async_start_full_cycle(coordinator: "RainBirdSchedulerCoordinator") -> None:
    """Run all zones for their configured durations, cycles_per_run times."""
    _LOGGER.info("[stub] start_full_cycle")


async def async_start_test_cycle(coordinator: "RainBirdSchedulerCoordinator") -> None:
    """Run all zones for 1 minute each, calibrating GPM via Flume per zone."""
    _LOGGER.info("[stub] start_test_cycle")


async def async_stop_all(coordinator: "RainBirdSchedulerCoordinator") -> None:
    """Stop any running cycle/scripts and turn off all rainbird switches."""
    _LOGGER.info("[stub] stop_all")
