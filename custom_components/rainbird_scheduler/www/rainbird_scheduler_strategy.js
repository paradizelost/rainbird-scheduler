/*
 * Rain Bird Scheduler Lovelace strategy
 *
 * Auto-generates a dashboard from rainbird_scheduler entities. Uses ONLY
 * built-in Lovelace cards (no HACS frontend dependencies) so a fresh HA
 * install gets a working UI out of the box.
 *
 * Usage:
 *   Settings → Dashboards → Add → from strategy:
 *     type: custom:rainbird-scheduler
 *
 * Discovers zones by scanning hass.entities for entities matching
 *   number.<prefix>_zone_N_minutes
 * and groups them by zone N. Any zone with a minutes entity becomes
 * a card; zone friendly names come from the matching entity's name.
 */

class RainbirdSchedulerStrategy extends HTMLElement {
  static async generate(config, hass) {
    const states = hass.states;

    // Discover our entities via the entity registry, keyed by `unique_id`.
    // unique_id is integration-controlled (`<config_entry_id>_<role>`) and is
    // stable across device/entity renames — exactly what we want to key cards
    // off, instead of guessing display-name slugs.
    //
    // IMPORTANT: `hass.entities` (the client-side *display* registry) does NOT
    // carry `unique_id` — only entity_id/platform/device_id/area_id/name/etc.
    // The full registry (with unique_id) only comes over the WebSocket, so we
    // fetch it here. `generate` is async, so the await is fine.
    let registry = [];
    try {
      registry = await hass.callWS({ type: "config/entity_registry/list" });
    } catch (err) {
      // Older HA or a restricted user: fall back to the display registry
      // below. Without unique_id we can only best-effort match by entity_id,
      // which breaks under custom entity names — but it beats a blank board.
      console.warn(
        "rainbird-scheduler strategy: config/entity_registry/list failed; " +
          "falling back to entity_id matching",
        err
      );
    }

    // Build a role → entity_id map. Role is whatever follows the first `_` in
    // unique_id, since config_entry_ids are ULIDs/hex with no underscores.
    const byRole = {};
    if (registry.length) {
      for (const e of registry) {
        if (e.platform !== "rainbird_scheduler") continue;
        if (!e.unique_id || !e.entity_id) continue;
        const idx = e.unique_id.indexOf("_");
        if (idx < 0) continue;
        byRole[e.unique_id.slice(idx + 1)] = e.entity_id;
      }
    } else {
      // Degraded fallback: derive a pseudo-role from the entity_id suffix.
      // Only matches installs that kept default entity names; custom-named
      // zones won't be found, but core cards still populate.
      const display = Object.values(hass.entities || {}).filter(
        (e) => e.platform === "rainbird_scheduler"
      );
      for (const e of display) {
        if (!e.entity_id) continue;
        const m = e.entity_id.match(/^[^.]+\.rain_?bird_scheduler_(.+)$/);
        if (m) byRole[m[1]] = e.entity_id;
      }
    }

    const idFor = (role) => byRole[role] || null;
    const zoneEntity = (n, kind) => byRole[`zone_${n}_${kind}`] || null;

    // Zones: roles look like `zone_N_minutes`, pull N out of every minutes role.
    const zoneNums = Object.keys(byRole)
      .map((role) => {
        const m = role.match(/^zone_(\d+)_minutes$/);
        return m ? parseInt(m[1], 10) : null;
      })
      .filter((n) => n !== null)
      .sort((a, b) => a - b);

    // Map scheduler zone N -> the official Rain Bird valve switch (platform
    // "rainbird") whose `zone` attribute is N. This gives us (a) the user's
    // clean zone name ("South Boulevard" vs the scheduler entity's "Rain Bird
    // Scheduler South Boulevard Minutes") and (b) a live on/off signal for the
    // "running now" indicator. The scheduler depends on the rainbird
    // integration, so these switches exist.
    const zoneSwitch = {}; // N -> switch entity_id
    const zoneSwitchName = {}; // N -> friendly name
    const rbSource = registry.length
      ? registry.filter((e) => e.platform === "rainbird")
      : Object.values(hass.entities || {}).filter(
          (e) => e.platform === "rainbird"
        );
    for (const e of rbSource) {
      if (!e.entity_id || !e.entity_id.startsWith("switch.")) continue;
      const st = states[e.entity_id];
      const z = st && st.attributes ? st.attributes.zone : undefined;
      if (z === undefined || z === null) continue;
      zoneSwitch[z] = e.entity_id;
      if (st.attributes.friendly_name) zoneSwitchName[z] = st.attributes.friendly_name;
    }

    // Rain sensor + controller rain-delay also come from the rainbird
    // integration (not the scheduler), used by the status strip below.
    const rbIds = rbSource.map((e) => e.entity_id).filter(Boolean);
    const rainSensorEntity =
      rbIds.find((eid) => eid.startsWith("binary_sensor.")) || null;
    const controllerDelayEntity =
      rbIds.find((eid) => eid.startsWith("sensor.") && /delay/i.test(eid)) ||
      null;

    const zoneName = (n) => {
      // Prefer the valve's clean friendly name; fall back to the scheduler
      // entity name with the device prefix + " Minutes" suffix stripped.
      if (zoneSwitchName[n]) return zoneSwitchName[n];
      const eid = zoneEntity(n, "minutes");
      const fn = eid ? states[eid]?.attributes?.friendly_name || "" : "";
      return (
        fn
          .replace(/\s*Minutes$/i, "")
          .replace(/^Rain\s?Bird Scheduler\s+/i, "")
          .trim() || `Zone ${n}`
      );
    };

    const verdictEntity = idFor("today_will_run");
    const totalMinEntity = idFor("run_total_minutes");
    const nextWindowEntity = idFor("next_run_window");
    const upcomingEntity = idFor("upcoming_runs");
    const monthlyEntity = idFor("monthly_estimated_gallons");
    const runGalEntity = idFor("run_estimated_gallons");
    const lastRunGalEntity = idFor("last_run_gallons");
    const lastRunAtEntity = idFor("last_run_at");
    const activityLogEntity = idFor("activity_log");
    const dayClassEntity = idFor("day_class");
    const everyNthEntity = idFor("every_nth");
    const cyclesEntity = idFor("cycles_per_run");
    const startTimeEntity = idFor("start_time");
    const anchorDateEntity = idFor("anchor_date");
    const scheduleEnabledEntity = idFor("schedule_enabled");
    const skipNextEntity = idFor("skip_next");
    const showDurationsEntity = idFor("show_durations");
    const rainDelayEntity = idFor("rain_delay");
    const weekdayEntities = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"].map(
      (d) => ({ wd: d, eid: idFor(`weekday_${d}`) })
    );

    // ---- Sprinkler title + verdict header
    const headerCard = {
      type: "markdown",
      content: `## Sprinkler Schedule
**Status:** {{ states('${verdictEntity}') }}
**Next window:** {{ states('${nextWindowEntity}') }} ({{ states('${totalMinEntity}') }} min)
**Upcoming:** {{ states('${upcomingEntity}') }}`,
    };

    // ---- Status strip (restored from v1.0): rain sensor, rain delay,
    // schedule enabled, skip-next. Built as colored markdown spans (built-in
    // glance/entities can't do per-state custom colors). All low-frequency
    // entities, so safe in a template card. Uses HA theme color vars.
    const statusParts = [];
    if (rainSensorEntity) {
      statusParts.push(
        `{% set rain = is_state('${rainSensorEntity}', 'on') %}` +
          `<span style="color: var(--{{ 'info-color' if rain else 'disabled-text-color' }})">` +
          `🌧️ {{ 'Rain detected' if rain else 'No rain' }}</span>`
      );
    }
    const delayExprs = [];
    if (controllerDelayEntity)
      delayExprs.push(`states('${controllerDelayEntity}') | int(0)`);
    if (rainDelayEntity) delayExprs.push(`states('${rainDelayEntity}') | int(0)`);
    if (delayExprs.length) {
      const delayExpr =
        delayExprs.length > 1 ? `[${delayExprs.join(", ")}] | max` : delayExprs[0];
      statusParts.push(
        `{% set delay = ${delayExpr} %}` +
          `<span style="color: var(--{{ 'warning-color' if delay > 0 else 'disabled-text-color' }})">` +
          `⏳ Delay {{ delay }}d</span>`
      );
    }
    if (scheduleEnabledEntity) {
      statusParts.push(
        `{% set en = is_state('${scheduleEnabledEntity}', 'on') %}` +
          `<span style="color: var(--{{ 'success-color' if en else 'disabled-text-color' }})">` +
          `📅 Schedule {{ 'on' if en else 'off' }}</span>`
      );
    }
    if (skipNextEntity) {
      statusParts.push(
        `{% set skip = is_state('${skipNextEntity}', 'on') %}` +
          `<span style="color: var(--{{ 'warning-color' if skip else 'disabled-text-color' }})">` +
          `⏭️ Skip next {{ 'on' if skip else 'off' }}</span>`
      );
    }
    const statusCard = statusParts.length
      ? { type: "markdown", content: statusParts.join(" &nbsp;·&nbsp; ") }
      : null;

    // ---- Settings card
    const settingsRows = [
      scheduleEnabledEntity,
      startTimeEntity,
      dayClassEntity,
      everyNthEntity,
      anchorDateEntity,
      cyclesEntity,
      skipNextEntity,
      rainDelayEntity,
    ].filter(Boolean);

    const weekdayRows = weekdayEntities.filter((w) => w.eid).map((w) => w.eid);

    const settingsCard = {
      type: "entities",
      title: "Master Settings",
      show_header_toggle: false,
      entities: settingsRows,
    };

    // Weekdays card — only relevant when day class = "day of week", so hide
    // it for even/odd/all via a conditional keyed on the day_class select.
    // (day_class options are: even, odd, all, day of week.)
    const weekdaysCard =
      weekdayRows.length && dayClassEntity
        ? {
            type: "conditional",
            conditions: [{ entity: dayClassEntity, state: "day of week" }],
            card: {
              type: "entities",
              title: "Weekdays",
              show_header_toggle: false,
              entities: weekdayRows,
            },
          }
        : null;

    // ---- Gallons tiles
    const tiles = {
      type: "glance",
      title: "Water usage",
      entities: [
        runGalEntity && { entity: runGalEntity, name: "Per run" },
        monthlyEntity && { entity: monthlyEntity, name: "Per month" },
        lastRunGalEntity && { entity: lastRunGalEntity, name: "Last run" },
        lastRunAtEntity && { entity: lastRunAtEntity, name: "Last run at" },
      ].filter(Boolean),
    };

    // ---- Activity log (the synthetic sensor — only explicit messages)
    const activityCard = activityLogEntity
      ? {
          type: "logbook",
          title: "Rainbird activity (last 14 days)",
          hours_to_show: 336,
          entities: [activityLogEntity],
        }
      : null;

    // ---- Schedule calendar — three stacked month grids: last / this / next
    // month. A reusable Jinja macro renders one month, called for the previous,
    // current, and next month. Run days are marked 💧 and today as [n].
    //
    // Two data sources, both YYYY-MM-DD strings from the `upcoming_runs`
    // sensor, so the template never re-derives any odd/even/every-Nth math:
    //   - `past_runs` — days the schedule ACTUALLY ran (recorded history),
    //     so the past portion reflects reality (rain-skipped days stay blank).
    //   - `dates`     — upcoming scheduled-eligible days (today → end of next
    //     month), so the future portion matches what the scheduler will do.
    // The union covers every cell; membership alone decides the 💧.
    //
    // Hand-rolled HTML table because the built-in `calendar` card hangs on some
    // setups. now() makes this re-render ~once/minute — low-frequency, safe.
    const calendarCard = upcomingEntity
      ? {
          type: "markdown",
          title: "Schedule Calendar",
          content: [
            `{% set today = now() %}`,
            `{% set runs = (state_attr('${upcomingEntity}', 'past_runs') or []) + (state_attr('${upcomingEntity}', 'dates') or []) %}`,
            // Skip indicators: rain delay marks the next N days as paused; the
            // skip-next toggle marks the single next eligible run. Both render as
            // 🚫 + a tinted cell so it's obvious the schedule won't run.
            rainDelayEntity
              ? `{% set rdays = states('${rainDelayEntity}') | int(0) %}`
              : `{% set rdays = 0 %}`,
            skipNextEntity
              ? `{% set skip_next_on = is_state('${skipNextEntity}', 'on') %}`
              : `{% set skip_next_on = false %}`,
            `{% set next_run = states('${upcomingEntity}') %}`,
            // month_grid(y, m): render one month as a labeled HTML table.
            `{% macro month_grid(y, m) %}`,
            `{% set first = today.replace(year=y, month=m, day=1) %}`,
            `{% set first_col = (first.weekday() + 1) % 7 %}`,
            `{% set last_day = (first + timedelta(days=32)).replace(day=1) - timedelta(days=1) %}`,
            `{% set dim = last_day.day %}`,
            `#### {{ first.strftime('%B %Y') }}`,
            ``,
            `<table style="width:100%;text-align:center;border-collapse:separate;border-spacing:6px 6px;font-size:14px;table-layout:fixed">`,
            `<tr><th style="opacity:0.6">S</th><th style="opacity:0.6">M</th><th style="opacity:0.6">T</th><th style="opacity:0.6">W</th><th style="opacity:0.6">T</th><th style="opacity:0.6">F</th><th style="opacity:0.6">S</th></tr>`,
            `<tr>`,
            `{%- for _ in range(first_col) %}<td></td>{%- endfor %}`,
            `{%- for d in range(1, dim + 1) -%}`,
            `{%- set cell = first.replace(day=d) -%}`,
            `{%- set daystr = '%04d-%02d-%02d' | format(y, m, d) -%}`,
            `{%- set offset = (cell.date() - today.date()).days -%}`,
            `{%- set is_run = daystr in runs -%}`,
            `{%- set is_today = (y == today.year and m == today.month and d == today.day) -%}`,
            `{%- set skipped = (offset >= 0 and offset < rdays) or (skip_next_on and daystr == next_run) -%}`,
            `{%- set inner = ('<strong>[' ~ d ~ ']</strong>') if is_today else (d | string) -%}`,
            `{%- set marker = '🚫' if (skipped and is_run) else ('💧' if is_run else '') -%}`,
            `{%- set bg = ' style="background:rgba(244,67,54,0.18);border-radius:6px"' if skipped else '' -%}`,
            `<td{{ bg }}>{{ inner }}{{ marker }}</td>`,
            `{%- set col = (first_col + d) % 7 -%}`,
            `{%- if col == 0 and d != dim %}</tr><tr>{%- endif -%}`,
            `{%- endfor %}`,
            `{%- set used = first_col + dim -%}`,
            `{%- set pad = (7 - (used % 7)) % 7 -%}`,
            `{%- for _ in range(pad) %}<td></td>{%- endfor %}`,
            `</tr>`,
            `</table>`,
            `{% endmacro %}`,
            // Previous / current / next month indices (handle year wrap).
            `{% set cy = today.year %}{% set cm = today.month %}`,
            `{% set py = cy - 1 if cm == 1 else cy %}{% set pm = 12 if cm == 1 else cm - 1 %}`,
            `{% set ny = cy + 1 if cm == 12 else cy %}{% set nm = 1 if cm == 12 else cm + 1 %}`,
            `{{ month_grid(py, pm) }}`,
            `{{ month_grid(cy, cm) }}`,
            `{{ month_grid(ny, nm) }}`,
            ``,
            `{% if rdays > 0 %}<div style="color:var(--error-color)">🚫 Rain delay: {{ rdays }} day{{ 's' if rdays != 1 else '' }} skipped — no runs through {{ (today + timedelta(days=rdays - 1)).strftime('%a, %b ') }}{{ (today + timedelta(days=rdays - 1)).day }}</div>{% endif %}`,
            `{% if skip_next_on %}<div style="color:var(--warning-color)">🚫 Next scheduled run will be skipped</div>{% endif %}`,
            ``,
            `<span style="opacity:0.6">💧 ran / scheduled · 🚫 skipped · [n] today</span>`,
            ``,
            `**Next:** {{ strptime(states('${upcomingEntity}'), '%Y-%m-%d').strftime('%a, %b %-d') if states('${upcomingEntity}') not in ['unknown', 'unavailable', 'none'] else '—' }}`,
          ].join("\n"),
        }
      : null;

    // ---- Tomorrow's decision matrix (restored from v1.0). Every value here
    // comes from the integration's own decision (exposed as `tomorrow_*`
    // attributes on the verdict sensor) — the dashboard only FORMATS booleans,
    // it never re-derives day-class/eligibility math. That re-derivation is
    // what produced wrong dates before, so it stays out of the template.
    const decisionCard = verdictEntity
      ? {
          type: "markdown",
          title: "Tomorrow's decision",
          content: [
            `{% set v = state_attr('${verdictEntity}', 'tomorrow_verdict') %}`,
            `{% set dt = state_attr('${verdictEntity}', 'tomorrow_date') %}`,
            `{% set en = state_attr('${verdictEntity}', 'tomorrow_enabled') %}`,
            `{% set win = state_attr('${verdictEntity}', 'tomorrow_in_window') %}`,
            `{% set skip = state_attr('${verdictEntity}', 'tomorrow_skip_next') %}`,
            `{% set wet = state_attr('${verdictEntity}', 'tomorrow_wet') %}`,
            `{% set rd = state_attr('${verdictEntity}', 'tomorrow_rain_delay_days') | int(0) %}`,
            `{% if v is none %}_Decision detail appears after the next Home Assistant restart._`,
            `{% else %}### {{ strptime(dt, '%Y-%m-%d').strftime('%A, %b %-d') if dt else 'Tomorrow' }} — *{{ v }}*`,
            ``,
            `| Gate | Want | Tomorrow | OK |`,
            `|---|---|---|:--:|`,
            `| Schedule enabled | on | {{ 'on' if en else 'off' }} | {{ '✅' if en else '❌' }} |`,
            `| Day in window | yes | {{ 'yes' if win else 'no' }} | {{ '✅' if win else '❌' }} |`,
            `| Skip-next | off | {{ 'on' if skip else 'off' }} | {{ '✅' if not skip else '❌' }} |`,
            `| Rain sensor | dry | {{ 'wet' if wet else 'dry' }} | {{ '✅' if not wet else '❌' }} |`,
            `| Rain delay | 0 | {{ rd }}d | {{ '✅' if rd == 0 else '❌' }} |`,
            ``,
            `_Rain & delay are current snapshots, not an overnight forecast — the morning re-check decides for real._`,
            `{% endif %}`,
          ].join("\n"),
        }
      : null;

    // ---- Zone cards (compact: name + configured runtime/flow + last-run as
    // read-only text + a Run-now button). The settings line and last-run go in
    // a `markdown` card on purpose:
    //   - `last_run` is a `datetime` entity; in an `entities` card it renders
    //     as an editable date/time *picker*, which we don't want for history.
    //   - templated text won't evaluate in an `entities`-card `section` label.
    // markdown handles both. These values only change on edit / run completion,
    // so this is not a high-frequency template card.
    // Editable runtime/GPM fields live in their own toggleable sections below.
    const zoneCards = zoneNums.map((n) => {
      const lastRun = zoneEntity(n, "last_run");
      const minutes = zoneEntity(n, "minutes");
      const gpm = zoneEntity(n, "gpm");
      const name = zoneName(n);
      const sw = zoneSwitch[n]; // official Rain Bird valve switch, if found
      const subParts = [
        minutes && `{{ states('${minutes}') | int(0) }} min`,
        gpm && `{{ states('${gpm}') | float(0) }} gpm`,
      ].filter(Boolean);
      const idleLines = [];
      if (subParts.length) idleLines.push(`Configured: ${subParts.join(" · ")}`);
      if (lastRun) {
        // as_timestamp(..., None) → None for unknown/unavailable, so the
        // conditional cleanly falls back to "never" instead of erroring.
        idleLines.push(
          `Last run: {{ as_timestamp(states('${lastRun}'), None) | ` +
            `timestamp_custom('%b %-d, %-I:%M %p') ` +
            `if as_timestamp(states('${lastRun}'), None) else 'never' }}`
        );
      }
      const idleBlock = idleLines.join("  \n");
      // When the zone's valve is on, show a "running now" line (v1.0 style) in
      // place of the idle info. The valve switch toggles only a few times per
      // run, so this is not a high-frequency template.
      let body = idleBlock;
      if (sw) {
        const runMin = minutes
          ? ` · {{ states('${minutes}') | int(0) }} min`
          : "";
        body =
          `{% if is_state('${sw}', 'on') %}` +
          `<span style="color: var(--info-color)"><b>● Running now</b></span>${runMin}` +
          ` · started {{ as_timestamp(states['${sw}'].last_changed) | timestamp_custom('%-I:%M %p') }}` +
          `{% else %}${idleBlock}{% endif %}`;
      }
      // One compact row per zone: name + status/info on the left (markdown, so
      // values render as read-only text and the running line can be styled),
      // and the Run-now button beside it on the same row.
      return {
        type: "horizontal-stack",
        cards: [
          {
            type: "markdown",
            content: `### ${name}` + (body ? `\n\n${body}` : ""),
          },
          {
            type: "button",
            name: "Run now",
            icon: "mdi:sprinkler",
            show_state: false,
            tap_action: {
              action: "call-service",
              service: "rainbird_scheduler.start_zone",
              service_data: { zone: n },
              confirmation: {
                text: `Run ${name} for its configured duration?`,
              },
            },
          },
        ],
      };
    });

    // ---- Toggleable "Edit zone runtimes" card.
    // Revealed when switch.<...>_show_durations is on. One row per zone
    // with the minutes number entity; HA renders the number with inline
    // +/- controls when the entity's mode is `box`.
    const editDurationsCard =
      showDurationsEntity && zoneNums.length
        ? {
            type: "conditional",
            conditions: [{ entity: showDurationsEntity, state: "on" }],
            card: {
              type: "entities",
              title: "Edit zone runtimes (minutes)",
              show_header_toggle: false,
              entities: zoneNums
                .map((n) => {
                  const eid = zoneEntity(n, "minutes");
                  return eid ? { entity: eid, name: zoneName(n) } : null;
                })
                .filter(Boolean),
            },
          }
        : null;

    // ---- Toggleable "Edit GPM calibration" card.
    const editGpmCard =
      showDurationsEntity && zoneNums.length
        ? {
            type: "conditional",
            conditions: [{ entity: showDurationsEntity, state: "on" }],
            card: {
              type: "entities",
              title: "Edit zone flow calibration (GPM)",
              show_header_toggle: false,
              entities: zoneNums
                .map((n) => {
                  const eid = zoneEntity(n, "gpm");
                  return eid ? { entity: eid, name: zoneName(n) } : null;
                })
                .filter(Boolean),
            },
          }
        : null;

    // ---- "Show editor" toggle chip. Always visible so users can flip into
    // edit mode without diving into Settings.
    const editorToggleCard = showDurationsEntity
      ? {
          type: "entities",
          show_header_toggle: false,
          entities: [
            {
              entity: showDurationsEntity,
              name: "Show duration / GPM editors",
              icon: "mdi:timer-cog-outline",
            },
          ],
        }
      : null;

    // ---- Action buttons
    const actionsCard = {
      type: "horizontal-stack",
      cards: [
        {
          type: "button",
          name: "Run Full Cycle",
          icon: "mdi:play-circle",
          tap_action: {
            action: "call-service",
            service: "rainbird_scheduler.start_full_cycle",
            confirmation: {
              text: "Run all zones for their configured durations now?",
            },
          },
        },
        {
          type: "button",
          name: "Test Cycle (1 min/zone)",
          icon: "mdi:test-tube",
          tap_action: {
            action: "call-service",
            service: "rainbird_scheduler.start_test_cycle",
            confirmation: {
              text: "Run all zones for 1 minute each to calibrate GPM?",
            },
          },
        },
        {
          type: "button",
          name: "Stop All",
          icon: "mdi:stop-circle",
          tap_action: {
            action: "call-service",
            service: "rainbird_scheduler.stop_all",
          },
        },
      ],
    };

    // Group cards into type-based sections. Each section is atomic — the
    // Sections layout never splits one across columns — so a given kind of
    // card (e.g. the zones) always stays together, and HA tiles the grouped
    // blocks dynamically (collapsing to one column on narrow screens).
    const section = (title, cards) => {
      const filtered = cards.filter(Boolean);
      return filtered.length ? { type: "grid", title, cards: filtered } : null;
    };

    const sections = [
      section("Status", [headerCard, statusCard, tiles, actionsCard]),
      section("Calendar & Tomorrow", [calendarCard, decisionCard]),
      section("Zones", [...zoneCards]),
      section("Activity", [activityCard]),
      section("Settings", [
        settingsCard,
        weekdaysCard,
        editorToggleCard,
        editDurationsCard,
        editGpmCard,
      ]),
    ].filter(Boolean);

    return {
      title: "Rainbird",
      views: [
        {
          title: "Schedule",
          path: "schedule",
          icon: "mdi:sprinkler-variant",
          type: "sections",
          max_columns: 3,
          sections,
        },
      ],
    };
  }
}

// `customElements.define` throws if you register the same class under two
// names, so use a trivial subclass for each. Dashboard-level strategies
// (root-of-config `strategy:`) look up `ll-strategy-dashboard-<type>`;
// view-level strategies look up `ll-strategy-<type>`. We register both.
class RainbirdSchedulerDashboardStrategy extends RainbirdSchedulerStrategy {}

// Idempotent define — this module can be loaded more than once (e.g. via
// add_extra_js_url *and* a leftover manual Lovelace resource), and a second
// `customElements.define` of an existing name throws, which would abort the
// rest of the module.
const defineOnce = (name, cls) => {
  if (!customElements.get(name)) customElements.define(name, cls);
};
defineOnce("ll-strategy-rainbird-scheduler", RainbirdSchedulerStrategy);
defineOnce(
  "ll-strategy-dashboard-rainbird-scheduler",
  RainbirdSchedulerDashboardStrategy
);
