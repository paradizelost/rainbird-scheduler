# Rain Bird Scheduler

Scheduling, calibration, and a dashboard on top of Home Assistant's built-in
[Rain Bird](https://www.home-assistant.io/integrations/rainbird/) controller integration.

## What you get

- **Per-zone runtime + GPM calibration** as `number` entities, auto-created from your loaded Rain Bird zones.
- **Per-zone last-run timestamps** as `datetime` entities — persists across restarts.
- **Day-class / every-Nth scheduling** (even / odd / every N days / day-of-week, with anchor).
- **Skip gates**: rain sensor wet, controller rain delay, manual skip, schedule disabled.
- **Race-free scheduled run** — verdict computed inline at fire time, no template-sensor cache lag at midnight.
- **Services**: `start_zone`, `start_full_cycle`, `start_test_cycle` (calibrates GPM), `stop_all`.
- **Activity logbook sensor** — synthetic channel that captures only the integration's explicit messages.
- **Auto-generated Lovelace dashboard** via strategy — works with only built-in cards.

## Requirements

- Home Assistant 2024.6+
- Built-in **Rain Bird** integration configured with at least one zone
- *(Optional)* **Flume** integration for GPM auto-calibration via flow measurement

## Setup after install

1. Restart Home Assistant.
2. Settings → Devices & Services → Add Integration → "Rain Bird Scheduler".
3. (Optional) Settings → Dashboards → Add Dashboard → from strategy → `custom:rainbird-scheduler`.

History and roadmap in the [README](https://github.com/paradizelost/rainbird-scheduler#readme).
