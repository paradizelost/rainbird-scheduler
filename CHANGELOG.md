# Changelog

All notable changes to this project will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [SemVer](https://semver.org/).

## [Unreleased]

## [0.1.2] — 2026-05-27

### Fixed
- **Dashboard showed all sensor values as "unknown"** because the strategy's
  entity matcher looked for `rainbird_scheduler_` in entity IDs, but HA
  slugifies the default device name "Rain Bird Scheduler" to
  `rain_bird_scheduler` (with underscores between words). The matcher now
  accepts both `rainbird_scheduler` and `rain_bird_scheduler` via regex.

### Known limitations
- Dashboard discovery still depends on the device name slug containing some
  variant of "rainbird_scheduler". Renaming the device to something without
  "rainbird" or "rain_bird" will break the strategy until v0.2 switches to
  registry-based lookup.

## [0.1.1] — 2026-05-27

### Fixed
- **Dashboard strategy now registers correctly.** `customElements.define`
  throws on duplicate class registration, so the dashboard-level element
  (`ll-strategy-dashboard-rainbird-scheduler`) was never registered after
  the view-level one (`ll-strategy-rainbird-scheduler`) registered first.
  Use a trivial subclass for the dashboard variant.

### Documented
- Manual Lovelace resource registration step in README — `add_extra_js_url`
  serves the JS but doesn't auto-register custom elements; users must add
  `/rainbird_scheduler_files/strategy.js` as a JavaScript-module resource
  under Settings → Dashboards → Resources until v0.2 auto-registers it.

## [0.1.0] — 2026-05-27

### Added
- Initial HACS-compatible release of the integration.
- Auto-discovery of Rain Bird zones from the loaded `rainbird` integration.
- Coordinator with persistent state (Store) for per-zone runtime, GPM, and
  last-run timestamps that survive HA restarts.
- Pure-function scheduler module (`scheduler.py`) with unit tests covering
  the v1.0.0 YAML package's eligibility + verdict logic, including
  regression tests for the 2026-05-26 midnight-race incidents.
- Race-free scheduled-run dispatch: time listener computes verdict inline
  via `coordinator.current_verdict()`, no cached template-sensor read.
- Entity platforms: `number` (per-zone minutes/GPM + every_nth, cycles,
  rain delay, last-run gallons), `datetime` (anchor date, last run at,
  per-zone last run), `time` (daily start time), `select` (day class),
  `switch` (schedule enabled, skip next, show durations, 7× weekdays),
  `sensor` (verdict, totals, next window, gallons estimates, upcoming
  runs, activity log).
- Services under domain `rainbird_scheduler`: `start_zone`,
  `start_full_cycle`, `start_test_cycle`, `stop_all`.
- Lovelace strategy (`custom:rainbird-scheduler`) that auto-generates a
  dashboard from discovered entities using only built-in cards.
- Synthetic activity-log sensor for clean dashboard logbook (no context-
  chain noise from script state toggles).

### Notes
- Replaces [`rainbird-ha-package`](https://git.hamik.net/claude-bot/rainbird-ha-package)
  v1.0.0 for users who want HACS-driven install/updates. The YAML version
  remains available at its v1.0.0 tag for `/config/packages/` users.
