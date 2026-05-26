# Changelog

All notable changes to this project will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [SemVer](https://semver.org/).

## [Unreleased]

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
