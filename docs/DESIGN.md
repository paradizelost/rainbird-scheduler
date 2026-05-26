# Design notes

## Why this exists

Home Assistant's built-in `rainbird` integration exposes zone switches and a
`start_irrigation` service, but no scheduler. Built-in HA automations work for
simple cases; once you want "every Nth even day" + rain-sensor skip + manual
skip + GPM calibration + a usable dashboard, the YAML grows past what's
maintainable as one-off config. This integration packages those pieces.

The mature YAML-package version lives at
[`rainbird-ha-package` v1.0.0](https://git.hamik.net/claude-bot/rainbird-ha-package/releases/tag/v1.0.0)
for users who prefer a `/config/packages/` drop-in.

## Architecture

```
┌──────────────┐                                  ┌──────────────────────┐
│  Rain Bird   │   switch.* + rainbird.svc        │  rainbird_scheduler  │
│  integration │  ◀──── reads zones, fires ─────  │                      │
└──────────────┘                                  └──────────┬───────────┘
                                                             │
                              ┌──────────────────────────────┴───────────┐
                              │                                          │
                  ┌───────────▼───────────┐                  ┌───────────▼───────────┐
                  │     Coordinator       │                  │     Entity platforms  │
                  │ - State (Store)       │                  │ number / datetime /   │
                  │ - Verdict (scheduler) │  ◀── proxies ──  │ time / select /       │
                  │ - Time listener       │                  │ switch / sensor       │
                  │ - Zone discovery      │                  └───────────────────────┘
                  └───────────┬───────────┘
                              │
                  ┌───────────▼───────────┐
                  │      Runner           │
                  │ start_zone /          │  ◀── calls rainbird.start_irrigation,
                  │ start_full_cycle /    │      switch.turn_off, logbook.log
                  │ start_test_cycle /    │
                  │ stop_all              │
                  └───────────────────────┘
```

### State lives in the coordinator, not entities

All persisted state (per-zone minutes, GPM, last-run, schedule shape,
toggles) lives in `CoordinatorState`. Entities are thin proxies — they
read coordinator state via `native_value` / `is_on` / `current_option`
and write via coordinator mutators that auto-persist.

This means:
- Adding a new entity is cheap (just a property + one mutator call).
- Migrating between HA versions doesn't churn `.storage` entity files.
- Tests can exercise scheduler logic without instantiating entities.

### Verdict computation is pure

`scheduler.compute_verdict(date, ScheduleConfig)` has zero HA dependencies
and is fully unit-tested. The coordinator builds a `ScheduleConfig` from
its current state plus the configured rain-sensor reading, then calls the
pure function. No caching — every call recomputes from current state.

### The midnight race is gone

The v1.0.0 YAML used a template sensor (`sensor.rainbird_today_will_run`)
that re-evaluated on minute boundaries via HA's time listener. When the
automation also fired at minute boundaries (start_time = 00:00:00), the
automation read the sensor ~150ms BEFORE the sensor re-rendered → got
yesterday's value. Symptoms:
- 2026-05-26 pandc (cls=odd/n=1): ran on day 26 (even = not eligible)
- 2026-05-26 homecontrol (cls=even/n=2 anchor=05-14): missed day 26
  (which IS eligible)

In the integration, the scheduled-run dispatch calls
`coordinator.current_verdict()` which computes inline — no cache, no
race. Regression tests for both incidents are in `tests/test_scheduler.py`.

### Activity log is a synthetic sensor

A constant-state template sensor (`sensor.<id>_activity_log`) acts as a
"log channel". Every `logbook.log` call from the integration attributes
to this entity. A dashboard logbook card watching ONLY this entity sees
exactly the messages we emit — no script on/off, no context-chain pull-in
of related switch state changes. Same trick the v1.0.0 YAML used,
implemented natively here.

### Per-zone last-run persists across restarts

In v1.0.0 we used `switch.last_changed` which resets to HA startup time
on every reboot. Here, each per-zone `datetime` entity is backed by
`CoordinatorState.zone_last_run[N]`, persisted via `Store`. Reboots
don't lose history.

### Cancellation

`stop_all` cancels the in-flight cycle by `task.cancel()` on the
coordinator's tracked `_active_cycle`. The currently-firing zone gets
a `switch.turn_off` in the `CancelledError` handler so we don't leave
a zone running after a cancel. Belt-and-suspenders: stop_all also fires
turn_off on every discovered zone.

## Dashboard strategy

`www/rainbird_scheduler_strategy.js` is registered as an extra Lovelace
JS module via `frontend.add_extra_js_url`. It exposes
`custom:rainbird-scheduler` as a strategy that scans `hass.states` at
render time, discovers zones from `number._zone_N_minutes` entities,
and builds a dashboard from built-in cards only. No HACS frontend
dependencies required.

A "deluxe" YAML variant using mushroom + auto-entities + html-template-card
will ship as `examples/dashboard-deluxe.yaml` in a later release for users
who already have those installed.

## Versioning

- **v1.x of `rainbird-ha-package`** — YAML-package drop-in, archived.
- **v0.x of this integration** — initial HACS-compatible release, breaking
  changes possible as we iterate.
- **v1.0.0+ of this integration** — stable API, no breaking changes without
  a major bump.
