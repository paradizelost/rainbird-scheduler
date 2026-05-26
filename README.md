# Rain Bird Scheduler

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

Scheduling, calibration, and dashboards on top of Home Assistant's built-in
[Rain Bird](https://www.home-assistant.io/integrations/rainbird/) controller integration.

> **Status:** v0.x — in active development. The mature YAML-package version
> lives at [`rainbird-ha-package` v1.0.0](https://git.hamik.net/claude-bot/rainbird-ha-package/releases/tag/v1.0.0)
> for anyone who prefers a `/config/packages/` drop-in.

## What it does

- **Per-zone runtime + GPM calibration** — `number.rainbird_scheduler_zone_N_minutes` and `number.rainbird_scheduler_zone_N_gpm`, auto-created from your loaded Rain Bird zones.
- **Per-zone last-run timestamps** — `datetime.rainbird_scheduler_zone_N_last_run`, persists across HA restarts.
- **Day-class / every-Nth schedule** — even / odd / day-of-week / arbitrary-N, with anchor date.
- **Skip gates** — rain sensor wet, controller rain delay, manual skip toggle, schedule disabled.
- **Race-free scheduled run** — verdict computed inline at fire time (no template-sensor cache lag at midnight).
- **Services** — `start_zone`, `start_full_cycle`, `start_test_cycle` (1 min/zone for GPM calibration), `stop_all`.
- **Activity logbook** — synthetic sensor that only captures explicit script messages (no noisy state toggles).
- **Auto-generated dashboard** — Lovelace strategy renders the full schedule UI from your discovered zones.

## Requirements

- Home Assistant 2024.6 or later
- The built-in **Rain Bird** integration configured with at least one zone
- *(Optional)* **Flume** integration for GPM calibration via flow measurement

## Install

### Via HACS

1. HACS → Integrations → ⋮ → Custom repositories
2. Add `https://github.com/paradizelost/rainbird-scheduler` as an *Integration*
3. Install "Rain Bird Scheduler"
4. Restart Home Assistant
5. Settings → Devices & Services → Add Integration → "Rain Bird Scheduler"

### Manual

Copy `custom_components/rainbird_scheduler/` into your HA `config/custom_components/` directory, restart, and add via the UI.

## Configuration

The integration auto-discovers your Rain Bird zones. During setup you can optionally point at:

- A **Flume** daily-total sensor (e.g. `sensor.flume_sensor_home_current_day`) — used to measure GPM during runs and update the per-zone calibration.
- A **rain sensor** binary_sensor — when `on`, scheduled runs skip with reason `skip-rain`.

Both are optional; if omitted, GPM calibration is manual and rain-sensor skip is disabled.

## Acknowledgements

Iterated on with [Claude Code](https://claude.com/claude-code). Architecture and design choices in [docs/DESIGN.md](docs/DESIGN.md).

## License

MIT
