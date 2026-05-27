# Changelog

All notable changes to this project will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [SemVer](https://semver.org/).

## [Unreleased]

## [0.1.11] — 2026-05-27

### Changed
- **Reordered into a single ordered column:** header, status icons, water
  usage, calendar, run/test/stop, zones, activity. Master Settings, Weekdays,
  and the runtime/GPM editor toggle now sit in a config footer below activity.
  (Single Sections column so the order is deterministic.)

## [0.1.10] — 2026-05-27

### Added
- **Status strip restored from v1.0** — a row of indicators under the header
  showing rain sensor (🌧️), effective rain delay (⏳, the max of the
  controller's and the scheduler's delay), schedule enabled (📅), and skip-next
  (⏭️), each colored by state via HA theme vars. The rain sensor and controller
  delay are pulled from the rainbird integration; schedule-enabled / skip-next
  from the scheduler.

## [0.1.9] — 2026-05-27

### Added
- **"Running now" status on zone cards, restored from v1.0.** When a zone's
  Rain Bird valve is on, its card shows "● Running now · N min · started
  HH:MM" in place of the configured/last-run text, keyed off the official
  rainbird switch's live state.

### Changed
- **Zone cards now use the valve's clean name** (e.g. "South Boulevard")
  instead of the scheduler entity's "Rain Bird Scheduler South Boulevard".
  Each scheduler zone is mapped to its rainbird switch via the switch's `zone`
  attribute, and that switch's friendly name is used as the zone title.

## [0.1.8] — 2026-05-27

### Changed
- **Switched the dashboard to the Sections layout.** Masonry was distributing
  cards by height and scattering the per-zone cards across both columns.
  Sections keeps grouped areas together and ordered: an Overview section
  (status, settings, calendar, water usage, activity) and a Zones section with
  the bulk actions (Test / Full Cycle / Stop) first, then the runtime/GPM
  editors, then all zone cards as one block.

## [0.1.7] — 2026-05-27

### Changed
- **Per-zone Run-now button now sits on the same row** as the zone's
  configured runtime/flow and last-run text, instead of on a separate row
  beneath it. Each zone is now a `horizontal-stack` of its info (markdown) +
  the Run button.

## [0.1.6] — 2026-05-27

### Added
- **Schedule Calendar** restored from the v1.0 YAML dashboard — a markdown
  month grid that marks upcoming run days with 💧 and today as `[n]`. Driven
  off the `upcoming_runs` sensor's `dates` attribute, so it reflects the
  scheduler's actual plan rather than re-derived date math. Hand-rolled HTML
  table because the built-in `calendar` card misbehaves on some setups.

### Changed
- **Weekday list is hidden unless Day Class = "day of week"** — wrapped in a
  `conditional` keyed on the day_class select, so even/odd/all modes no longer
  show an irrelevant weekday card.
- **Per-zone "Last run" now renders as read-only text** instead of an editable
  date/time picker. `last_run` is a `datetime` entity, which an `entities` card
  renders as an editable control; moved it into the zone's markdown card next
  to the configured runtime/flow.

## [0.1.5] — 2026-05-27

### Fixed
- **Dashboard rendered nearly empty** — header showed "unknown", Master
  Settings and Water usage cards were empty, and every zone card, the
  weekday list, the activity log, and the editor toggles were missing.
  v0.1.4 switched discovery to `unique_id` matching but read it from
  `hass.entities`, the client-side *display* registry, which carries
  `entity_id`/`platform`/`device_id` but **not** `unique_id`. Every entity
  was skipped, so no cards were populated.
- Strategy now fetches the full entity registry over the WebSocket
  (`config/entity_registry/list`), which does include `unique_id`, and keys
  role → entity_id off that. Falls back to entity_id matching only if the WS
  call fails (older HA / restricted user).
- **Zone-card "Configured: N min · M gpm" subtitle showed raw `{{ }}`
  template text.** It lived in an `entities`-card `section` label, which is
  plain text; moved it into a `markdown` card so the Jinja evaluates.
- **Frontend resource re-registered on every reload** — the idempotency
  guard called `getattr` on a dict (always falsy), so a reload hit
  `async_register_static_paths` twice. Uses a dict key now.
- `customElements.define` is now idempotent, so loading the strategy module
  more than once (e.g. a leftover manual Lovelace resource alongside the
  integration's auto-injected copy) no longer throws.

## [0.1.4] — 2026-05-27

### Fixed
- **Most entities silently missing from the dashboard** (no zone cards,
  no weekday switches, no Skip Next toggle, no Every Nth Day, no Show
  Durations toggle). Discovery was matching `entity_id.endsWith(role)`,
  but HA generates entity IDs from the display name not the integration's
  internal role — so `_skip_next` matcher missed `_skip_next_run` entity,
  `_every_nth` missed `_every_nth_day`, `_zone_5_minutes` missed
  `_south_yard_minutes`, etc.
- Strategy now uses the entity registry (`hass.entities`) and matches by
  `unique_id` instead, which IS role-based. Renaming the device no longer
  breaks discovery either.

### Closes
- Task that was originally scoped for v0.2 (registry-based lookup) —
  moved up because v0.1.3 surfaced how broken name-slug matching is in
  practice.

## [0.1.3] — 2026-05-27

### Changed
- **Dashboard now has dedicated editor sections** mirroring the v1.0 YAML
  UX. Each zone card is compact (current settings shown as a subtitle,
  last-run timestamp, and a Run-now button), and editing is exposed via a
  "Show duration / GPM editors" toggle that reveals two full-width
  `entities` cards listing every zone's minutes / GPM with inline +/-
  controls. Going to Settings → Devices & Services to bump a value is no
  longer necessary.

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
