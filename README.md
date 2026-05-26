# Rain Bird Scheduler

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Validate](https://github.com/paradizelost/rainbird-scheduler/actions/workflows/validate.yml/badge.svg)](https://github.com/paradizelost/rainbird-scheduler/actions/workflows/validate.yml)

Scheduling, calibration, and dashboards on top of Home Assistant's built-in
[Rain Bird](https://www.home-assistant.io/integrations/rainbird/) controller integration.

> **Status:** v0.x — initial HACS-compatible release.
> The mature YAML-package predecessor lives at
> [`rainbird-ha-package` v1.0.0](https://git.hamik.net/claude-bot/rainbird-ha-package/releases/tag/v1.0.0)
> for `/config/packages/` users.

## What it does

- **Per-zone runtime + GPM calibration** — `number.<...>_zone_N_minutes` and `number.<...>_zone_N_gpm`, auto-created from your loaded Rain Bird zones.
- **Per-zone last-run timestamps** — `datetime.<...>_zone_N_last_run`, persists across HA restarts.
- **Day-class / every-Nth schedule** — even / odd / day-of-week / arbitrary-N with anchor date.
- **Skip gates** — rain sensor wet, controller rain delay, manual skip toggle, schedule disabled.
- **Race-free scheduled run** — verdict computed inline at fire time, no template-sensor cache lag at midnight (see [DESIGN.md](docs/DESIGN.md#the-midnight-race-is-gone) for the bug it fixes).
- **Services** — `start_zone`, `start_full_cycle`, `start_test_cycle` (1 min/zone GPM calibration), `stop_all`.
- **Activity logbook sensor** — synthetic channel; only explicit messages, no state-change noise.
- **Auto-generated dashboard** — Lovelace strategy `custom:rainbird-scheduler` renders the full UI from discovered zones using built-in cards (no HACS frontend deps).

## Requirements

- Home Assistant **2024.6** or later
- Built-in **Rain Bird** integration configured with at least one zone
- *(Optional)* **Flume** integration if you want automatic GPM calibration from flow measurements

## Install

### Via HACS (custom repository)

1. HACS → Integrations → ⋮ → Custom repositories
2. Add `https://github.com/paradizelost/rainbird-scheduler` as an **Integration**
3. Install "Rain Bird Scheduler"
4. Restart Home Assistant
5. Settings → Devices & Services → Add Integration → "Rain Bird Scheduler"

### Manual

Copy `custom_components/rainbird_scheduler/` into your HA `config/custom_components/` directory, restart, and add via the UI.

## Configuration

On setup, the integration:

1. Discovers your Rain Bird zones via the entity registry.
2. Optionally accepts a Flume daily-total sensor (e.g. `sensor.flume_sensor_home_current_day`) for auto GPM calibration.
3. Optionally accepts a rain-sensor `binary_sensor` — when `on`, scheduled runs skip with reason `skip-rain`.

All schedule shape is configured through entities once set up:

| Entity | Purpose |
|--------|---------|
| `switch.<>_schedule_enabled` | Master on/off |
| `time.<>_start_time` | Daily start time (changing this re-arms the scheduler) |
| `select.<>_day_class` | even / odd / all / day of week |
| `number.<>_every_nth` | "Every Nth qualifying day" |
| `datetime.<>_anchor_date` | Origin date for `all` and weekly-rotation modes |
| `switch.<>_weekday_{mon..sun}` | Per-weekday toggles (when day class = "day of week") |
| `number.<>_cycles_per_run` | Repeat the full cycle N times per scheduled run |
| `switch.<>_skip_next` | One-shot manual skip |
| `number.<>_rain_delay` | Bidirectional with the controller's rain-delay number |
| `number.<>_zone_N_minutes` | Per-zone runtime |
| `number.<>_zone_N_gpm` | Per-zone flow rate (auto-calibrated by test/full cycle) |

## Dashboard

Settings → Dashboards → Add Dashboard → from strategy:

```yaml
strategy:
  type: custom:rainbird-scheduler
```

The strategy auto-generates a dashboard from your discovered zones using only built-in Lovelace cards. For a more polished version with mushroom + auto-entities, see `examples/dashboard-deluxe.yaml` *(coming soon)*.

## Services

```yaml
# Run a single zone (optional minutes override)
service: rainbird_scheduler.start_zone
data:
  zone: 3
  minutes: 15      # optional; defaults to the stored zone minutes

# Run all zones for their configured minutes × cycles_per_run
service: rainbird_scheduler.start_full_cycle

# Run all zones for 1 minute each, calibrating per-zone GPM via Flume
service: rainbird_scheduler.start_test_cycle

# Cancel the in-flight cycle and turn off every Rain Bird zone
service: rainbird_scheduler.stop_all
```

## Migration from `rainbird-ha-package` v1.0.0

1. **Back up** — `tar czf rainbird-yaml-backup.tgz /config/packages/rainbird.yaml /config/dashboards/rainbird.yaml`
2. Remove the package: delete `/config/packages/rainbird.yaml`. Restart HA to drop the helpers/scripts/automations. (Or use the UI to delete the orphaned entities afterward.)
3. Delete the YAML-mode rainbird dashboard from Settings → Dashboards.
4. Install this integration (steps above). Per-zone minutes/GPM will start at zero — re-enter them in the integration's `number` entities, or run a Test Cycle to calibrate GPM.
5. Re-create the dashboard from the `custom:rainbird-scheduler` strategy.

Entity IDs DO change (new domain prefix), so any external automations referencing the old `input_number.rainbird_zone_*` etc. need updating.

## Architecture

See [docs/DESIGN.md](docs/DESIGN.md) for the coordinator/runner/strategy split and a deep-dive on the midnight-race fix that motivated the rewrite.

## Acknowledgements

Iterated on with [Claude Code](https://claude.com/claude-code).

## License

MIT — see [LICENSE](LICENSE).
