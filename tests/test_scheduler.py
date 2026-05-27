"""Unit tests for the pure-function scheduler module.

These have no HA dependencies and verify the YAML→Python port of the
eligibility + verdict logic matches v1.0.0 behavior. Run with:

    python -m pytest tests/test_scheduler.py
"""

from __future__ import annotations

import sys
from datetime import date, datetime, time
from pathlib import Path

# Allow `from custom_components.rainbird_scheduler.scheduler import ...`
sys.path.insert(0, str(Path(__file__).parent.parent))

from custom_components.rainbird_scheduler.const import (
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
from custom_components.rainbird_scheduler.scheduler import (
    ScheduleConfig,
    compute_verdict,
    decision_breakdown,
    is_eligible,
    next_fire_datetime,
    next_run_date,
    runs_in_next_30_days,
)


# ------------------------------------------------------- decision_breakdown


class TestDecisionBreakdown:
    """The breakdown must agree with compute_verdict and report each gate, so
    the dashboard never re-derives the logic."""

    def test_breakdown_yes(self):
        cfg = ScheduleConfig(day_class=DAY_CLASS_EVEN, every_nth=1)
        d = decision_breakdown(date(2026, 5, 2), cfg)  # even day
        assert d["verdict"] == VERDICT_YES
        assert d == {
            "verdict": VERDICT_YES,
            "enabled": True,
            "in_window": True,
            "skip_next": False,
            "wet": False,
            "rain_delay_days": 0,
        }

    def test_breakdown_out_of_window(self):
        cfg = ScheduleConfig(day_class=DAY_CLASS_EVEN, every_nth=1)
        d = decision_breakdown(date(2026, 5, 3), cfg)  # odd day
        assert d["in_window"] is False
        assert d["verdict"] == VERDICT_SKIP_WINDOW

    def test_breakdown_matches_compute_verdict(self):
        cfg = ScheduleConfig(
            day_class=DAY_CLASS_EVEN, every_nth=1, skip_next=True
        )
        day = date(2026, 5, 2)
        assert decision_breakdown(day, cfg)["verdict"] == compute_verdict(day, cfg)
        assert decision_breakdown(day, cfg)["skip_next"] is True


# ---------------------------------------------------------------- is_eligible


class TestEligibilityEven:
    """cls=even: with n=1, every even day; n=2, every other even (~4 days)."""

    def test_even_n1_even_day_eligible(self):
        assert is_eligible(date(2026, 5, 2), ScheduleConfig(day_class=DAY_CLASS_EVEN, every_nth=1))
        assert is_eligible(date(2026, 5, 24), ScheduleConfig(day_class=DAY_CLASS_EVEN, every_nth=1))

    def test_even_n1_odd_day_not_eligible(self):
        assert not is_eligible(date(2026, 5, 3), ScheduleConfig(day_class=DAY_CLASS_EVEN, every_nth=1))
        assert not is_eligible(date(2026, 5, 25), ScheduleConfig(day_class=DAY_CLASS_EVEN, every_nth=1))

    def test_even_n2_pattern(self):
        # n=2: hits on 2, 6, 10, 14, 18, 22, 26, 30 (every other even)
        cfg = ScheduleConfig(day_class=DAY_CLASS_EVEN, every_nth=2)
        assert is_eligible(date(2026, 5, 2), cfg)
        assert is_eligible(date(2026, 5, 6), cfg)
        assert not is_eligible(date(2026, 5, 4), cfg)
        assert is_eligible(date(2026, 5, 26), cfg)
        assert not is_eligible(date(2026, 5, 24), cfg)


class TestEligibilityOdd:
    """cls=odd: with n=1, every odd day."""

    def test_odd_n1_odd_day_eligible(self):
        cfg = ScheduleConfig(day_class=DAY_CLASS_ODD, every_nth=1)
        assert is_eligible(date(2026, 5, 1), cfg)
        assert is_eligible(date(2026, 5, 25), cfg)
        assert is_eligible(date(2026, 5, 27), cfg)

    def test_odd_n1_even_day_not_eligible(self):
        cfg = ScheduleConfig(day_class=DAY_CLASS_ODD, every_nth=1)
        assert not is_eligible(date(2026, 5, 2), cfg)
        assert not is_eligible(date(2026, 5, 26), cfg)


class TestEligibilityAll:
    """cls=all: every Nth day from anchor."""

    def test_all_requires_anchor(self):
        cfg = ScheduleConfig(day_class=DAY_CLASS_ALL, every_nth=3, anchor_date=None)
        assert not is_eligible(date(2026, 5, 1), cfg)

    def test_all_n3_pattern(self):
        cfg = ScheduleConfig(
            day_class=DAY_CLASS_ALL, every_nth=3, anchor_date=date(2026, 5, 1)
        )
        assert is_eligible(date(2026, 5, 1), cfg)  # day 0
        assert is_eligible(date(2026, 5, 4), cfg)  # day 3
        assert is_eligible(date(2026, 5, 7), cfg)
        assert not is_eligible(date(2026, 5, 2), cfg)
        assert not is_eligible(date(2026, 5, 3), cfg)

    def test_all_before_anchor_not_eligible(self):
        cfg = ScheduleConfig(
            day_class=DAY_CLASS_ALL, every_nth=1, anchor_date=date(2026, 5, 10)
        )
        assert not is_eligible(date(2026, 5, 5), cfg)


class TestEligibilityDayOfWeek:
    """cls=day of week: specified weekdays, optionally every Nth week from anchor."""

    def test_dow_simple_weekdays(self):
        cfg = ScheduleConfig(
            day_class=DAY_CLASS_DAY_OF_WEEK,
            every_nth=1,
            weekdays={
                "mon": True,
                "tue": False,
                "wed": True,
                "thu": False,
                "fri": True,
                "sat": False,
                "sun": False,
            },
        )
        # 2026-05-04 is Mon, 2026-05-05 is Tue, 2026-05-06 is Wed
        assert is_eligible(date(2026, 5, 4), cfg)
        assert not is_eligible(date(2026, 5, 5), cfg)
        assert is_eligible(date(2026, 5, 6), cfg)

    def test_dow_every_other_week(self):
        # Every other Monday starting 2026-05-04
        cfg = ScheduleConfig(
            day_class=DAY_CLASS_DAY_OF_WEEK,
            every_nth=2,
            anchor_date=date(2026, 5, 4),
            weekdays={
                "mon": True,
                "tue": False,
                "wed": False,
                "thu": False,
                "fri": False,
                "sat": False,
                "sun": False,
            },
        )
        assert is_eligible(date(2026, 5, 4), cfg)  # week 0 Mon
        assert not is_eligible(date(2026, 5, 11), cfg)  # week 1 Mon
        assert is_eligible(date(2026, 5, 18), cfg)  # week 2 Mon
        assert not is_eligible(date(2026, 5, 25), cfg)  # week 3 Mon
        assert is_eligible(date(2026, 6, 1), cfg)  # week 4 Mon


# ------------------------------------------------------------ compute_verdict


class TestVerdictGates:
    """Gate ordering matters: disabled > out-of-window > skip > rain > delay > yes."""

    base_cfg = ScheduleConfig(day_class=DAY_CLASS_EVEN, every_nth=1, enabled=True)
    eligible_day = date(2026, 5, 2)  # even

    def test_yes_when_all_gates_green(self):
        assert compute_verdict(self.eligible_day, self.base_cfg) == VERDICT_YES

    def test_disabled_beats_all(self):
        cfg = ScheduleConfig(
            day_class=DAY_CLASS_EVEN, every_nth=1, enabled=False, skip_next=True, wet=True
        )
        assert compute_verdict(self.eligible_day, cfg) == VERDICT_DISABLED

    def test_skip_window_when_wrong_day(self):
        assert (
            compute_verdict(date(2026, 5, 3), self.base_cfg) == VERDICT_SKIP_WINDOW
        )

    def test_skip_manual_beats_rain_and_delay(self):
        cfg = ScheduleConfig(
            day_class=DAY_CLASS_EVEN,
            every_nth=1,
            enabled=True,
            skip_next=True,
            wet=True,
            rain_delay_days=2,
        )
        assert compute_verdict(self.eligible_day, cfg) == VERDICT_SKIP_MANUAL

    def test_skip_rain_beats_delay(self):
        cfg = ScheduleConfig(
            day_class=DAY_CLASS_EVEN,
            every_nth=1,
            enabled=True,
            wet=True,
            rain_delay_days=2,
        )
        assert compute_verdict(self.eligible_day, cfg) == VERDICT_SKIP_RAIN

    def test_skip_delay(self):
        cfg = ScheduleConfig(
            day_class=DAY_CLASS_EVEN, every_nth=1, enabled=True, rain_delay_days=2
        )
        assert compute_verdict(self.eligible_day, cfg) == VERDICT_SKIP_DELAY


# ---------------------------------------------------------- regression: midnight race


class TestRealIncidents:
    """Hard-coded checks from real-world bugs observed during v1.0 dev."""

    def test_pandc_may_26_2026_odd_n1(self):
        """pandc on 2026-05-26: cls=odd, n=1.

        May 26 is even — should be skip-window. (The v1.0.0 YAML midnight
        race caused 'yes' here from the stale sensor.)
        """
        cfg = ScheduleConfig(day_class=DAY_CLASS_ODD, every_nth=1, enabled=True)
        assert compute_verdict(date(2026, 5, 26), cfg) == VERDICT_SKIP_WINDOW
        assert compute_verdict(date(2026, 5, 25), cfg) == VERDICT_YES
        assert compute_verdict(date(2026, 5, 27), cfg) == VERDICT_YES

    def test_homecontrol_may_26_2026_even_n2_anchor_may_14(self):
        """homecontrol on 2026-05-26: cls=even, n=2, anchor=2026-05-14.

        With cls=even/n=2, eligible days are 2, 6, 10, 14, 18, 22, 26, 30.
        May 26 IS eligible. (The midnight race caused 'skip-window' from stale
        sensor evaluating for May 25 = odd day.)
        """
        cfg = ScheduleConfig(
            day_class=DAY_CLASS_EVEN,
            every_nth=2,
            enabled=True,
            anchor_date=date(2026, 5, 14),
        )
        assert compute_verdict(date(2026, 5, 26), cfg) == VERDICT_YES
        assert compute_verdict(date(2026, 5, 22), cfg) == VERDICT_YES
        assert compute_verdict(date(2026, 5, 30), cfg) == VERDICT_YES
        assert compute_verdict(date(2026, 5, 24), cfg) == VERDICT_SKIP_WINDOW


# ---------------------------------------------------------- helpers


class TestNextFireDatetime:
    def test_today_future_returns_today(self):
        now = datetime(2026, 5, 26, 10, 0, 0)
        fire = next_fire_datetime(now, time(15, 30, 0))
        assert fire == datetime(2026, 5, 26, 15, 30, 0)

    def test_today_past_returns_tomorrow(self):
        now = datetime(2026, 5, 26, 20, 0, 0)
        fire = next_fire_datetime(now, time(15, 30, 0))
        assert fire == datetime(2026, 5, 27, 15, 30, 0)

    def test_midnight_boundary_returns_tomorrow(self):
        """At exactly start_time, next fire is tomorrow (not now)."""
        now = datetime(2026, 5, 26, 0, 0, 0)
        fire = next_fire_datetime(now, time(0, 0, 0))
        assert fire == datetime(2026, 5, 27, 0, 0, 0)


class TestNextRunDate:
    def test_next_eligible_within_horizon(self):
        cfg = ScheduleConfig(day_class=DAY_CLASS_EVEN, every_nth=1)
        # Start on May 1 (odd day, n=1 even) — next even day is May 2
        assert next_run_date(date(2026, 5, 1), cfg) == date(2026, 5, 2)

    def test_today_eligible(self):
        cfg = ScheduleConfig(day_class=DAY_CLASS_EVEN, every_nth=1)
        assert next_run_date(date(2026, 5, 2), cfg) == date(2026, 5, 2)


class TestRunsPerMonth:
    def test_even_n1_about_15_per_month(self):
        cfg = ScheduleConfig(day_class=DAY_CLASS_EVEN, every_nth=1)
        # Start on May 1: next 30 days = May 1 through May 30.
        # Even days in [1, 30] = 2, 4, 6, ..., 30 = 15 days.
        assert runs_in_next_30_days(date(2026, 5, 1), cfg) == 15
