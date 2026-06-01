"""Pure-function eligibility + verdict logic for Rain Bird Scheduler.

Mirrors the gating logic from the v1.0.0 YAML package's
sensor.rainbird_today_will_run + the inline-verdict automation. Pure functions
with no HA dependencies — easy to unit-test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .const import (
    DAY_CLASS_ALL,
    DAY_CLASS_DAY_OF_WEEK,
    DAY_CLASS_EVEN,
    DAY_CLASS_ODD,
    VERDICT_DISABLED,
    VERDICT_SKIP_DELAY,
    VERDICT_SKIP_MANUAL,
    VERDICT_SKIP_RAIN,
    VERDICT_SKIP_WINDOW,
    VERDICT_YES,
)

WEEKDAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


@dataclass
class ScheduleConfig:
    """Configuration that drives eligibility decisions.

    Decoupled from HA entity state for testability. The coordinator builds
    one of these from its current entity-backed state before each check.
    """

    day_class: str = DAY_CLASS_EVEN
    every_nth: int = 1
    anchor_date: date | None = None
    weekdays: dict[str, bool] = field(
        default_factory=lambda: {wd: True for wd in WEEKDAY_NAMES}
    )
    enabled: bool = True
    skip_next: bool = False
    wet: bool = False
    rain_delay_days: int = 0


def is_eligible(day: date, config: ScheduleConfig) -> bool:
    """Is `day` in the schedule's day-class window?

    Even/odd: classic Rain Bird "every N even/odd days" pattern, with N=1
    meaning every even (or odd) day.

    All: every Nth day counting from anchor.

    Day-of-week: any enabled weekday; with N>1 + anchor, that weekday must
    also fall in a multiple-of-N-weeks slot from the anchor.

    Default (unknown class) falls back to even.
    """
    d = day.day
    n = max(1, config.every_nth)

    if config.day_class == DAY_CLASS_ODD:
        return d % 2 == 1 and (d - 1) % (2 * n) == 0

    if config.day_class == DAY_CLASS_ALL:
        if config.anchor_date is None:
            return False
        delta = (day - config.anchor_date).days
        return delta >= 0 and delta % n == 0

    if config.day_class == DAY_CLASS_DAY_OF_WEEK:
        wd_name = WEEKDAY_NAMES[day.weekday()]
        wd_on = config.weekdays.get(wd_name, False)
        if not wd_on:
            return False
        if config.anchor_date is None or n <= 1:
            return True
        delta_days = (day - config.anchor_date).days
        return delta_days >= 0 and (delta_days // 7) % n == 0

    # Default: even
    return d % 2 == 0 and (d - 2) % (2 * n) == 0


def compute_verdict(day: date, config: ScheduleConfig) -> str:
    """Compute today's verdict given config.

    Gate order matters: disabled > out-of-window > manual skip > rain >
    rain delay > yes. Matches the v1.0.0 sensor logic exactly so users
    moving from the YAML package see identical decisions.
    """
    if not config.enabled:
        return VERDICT_DISABLED
    if not is_eligible(day, config):
        return VERDICT_SKIP_WINDOW
    if config.skip_next:
        return VERDICT_SKIP_MANUAL
    if config.wet:
        return VERDICT_SKIP_RAIN
    if config.rain_delay_days > 0:
        return VERDICT_SKIP_DELAY
    return VERDICT_YES


def decision_breakdown(day: date, config: ScheduleConfig) -> dict[str, object]:
    """Per-gate breakdown for `day` plus the resulting verdict.

    Centralizes ALL decision logic here (and is unit-tested), so dashboards can
    render the result directly without re-deriving any day-class / eligibility
    math in templates — which is exactly the source of past wrong-date bugs.

    `in_window` is the day-class eligibility decision; the other gates mirror
    the precedence in `compute_verdict`.
    """
    return {
        "verdict": compute_verdict(day, config),
        "enabled": config.enabled,
        "in_window": is_eligible(day, config),
        "skip_next": config.skip_next,
        "wet": config.wet,
        "rain_delay_days": config.rain_delay_days,
    }


def upcoming_runs(start: date, config: ScheduleConfig, horizon_days: int = 60) -> list[date]:
    """Return eligible dates (window-only — doesn't consider rain/delay/skip)
    within the next `horizon_days` from `start` (inclusive)."""
    return [
        start + timedelta(days=offset)
        for offset in range(horizon_days)
        if is_eligible(start + timedelta(days=offset), config)
    ]


def runs_in_range(start: date, end: date, config: ScheduleConfig) -> list[date]:
    """Return eligible dates (window-only) in the inclusive range [start, end].

    Works backward and forward — `is_eligible` is pure, so this is also valid
    for past dates (used by the dashboard calendar to fill the future portion
    of the previous/current/next-month view). `end < start` yields []."""
    if end < start:
        return []
    span = (end - start).days
    return [
        start + timedelta(days=offset)
        for offset in range(span + 1)
        if is_eligible(start + timedelta(days=offset), config)
    ]


def next_run_date(start: date, config: ScheduleConfig, horizon_days: int = 60) -> date | None:
    """Return the next eligible date >= `start`, or None within horizon."""
    runs = upcoming_runs(start, config, horizon_days)
    return runs[0] if runs else None


def runs_in_next_30_days(start: date, config: ScheduleConfig) -> int:
    """Count eligible days in the next 30 (used for monthly estimates)."""
    return len(upcoming_runs(start, config, 30))


def next_fire_datetime(now: datetime, start_time, days_ahead_limit: int = 2) -> datetime:
    """Compute the next datetime at which the scheduled-run time listener
    should fire, given the configured daily `start_time` (a `datetime.time`).

    Returns today-at-start_time if that's still in the future; otherwise
    tomorrow-at-start_time. Used to schedule the time listener after
    initialization and after each fire.
    """
    candidate = now.replace(
        hour=start_time.hour,
        minute=start_time.minute,
        second=start_time.second,
        microsecond=0,
    )
    if candidate <= now:
        candidate += timedelta(days=1)
    if (candidate - now).days > days_ahead_limit:
        # Sanity: shouldn't happen, but guard against runaway scheduling
        candidate = now + timedelta(days=1)
    return candidate
