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

    // Find our entities via the entity registry (hass.entities). Each entry
    // has a stable `unique_id` formatted by the integration as
    // `<config_entry_id>_<role>` — independent of the device name slug HA
    // builds entity_ids from. This means a user renaming the device doesn't
    // break discovery, and we don't have to guess at display-name slugs.
    //
    // Falls back to {} if hass.entities is unavailable (older HA versions);
    // in that case the strategy will render mostly empty cards rather than
    // throwing.
    const allEntities = hass.entities || {};
    const ourEntities = Object.values(allEntities).filter(
      (e) => e.platform === "rainbird_scheduler"
    );

    // Build a role → entity_id map from unique_ids. Role is whatever comes
    // after the first `_` in unique_id, since config_entry_ids are 32-char
    // hex strings with no underscores.
    const byRole = {};
    for (const e of ourEntities) {
      if (!e.unique_id || !e.entity_id) continue;
      const idx = e.unique_id.indexOf("_");
      if (idx < 0) continue;
      byRole[e.unique_id.slice(idx + 1)] = e.entity_id;
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

    const zoneName = (n) => {
      const eid = zoneEntity(n, "minutes");
      if (!eid) return `Zone ${n}`;
      const fn = states[eid]?.attributes?.friendly_name || "";
      // Strip the " Minutes" suffix our entity adds
      return fn.replace(/\s+Minutes$/, "") || `Zone ${n}`;
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

    // Weekdays card — only relevant when day class = "day of week"; we show it
    // unconditionally for simplicity but mark it with a hint.
    const weekdaysCard = weekdayRows.length
      ? {
          type: "entities",
          title: 'Weekdays (used when day class = "day of week")',
          show_header_toggle: false,
          entities: weekdayRows,
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

    // ---- Zone cards (compact: name + last-run + Run-now button only).
    // Editable fields live in their own toggleable sections below so the
    // daily-use view stays uncluttered.
    const zoneCards = zoneNums.map((n) => {
      const lastRun = zoneEntity(n, "last_run");
      const minutes = zoneEntity(n, "minutes");
      const gpm = zoneEntity(n, "gpm");
      const name = zoneName(n);
      // Secondary text shows current runtime + GPM at a glance via templates
      // so users can see settings without flipping the editor toggle.
      const subtitle = [
        minutes && `{{ states('${minutes}') | int(0) }} min`,
        gpm && `{{ states('${gpm}') | float(0) }} gpm`,
      ]
        .filter(Boolean)
        .join(" · ");
      return {
        type: "entities",
        title: name,
        show_header_toggle: false,
        entities: [
          {
            type: "section",
            label: subtitle ? `Configured: ${subtitle}` : "Configured",
          },
          lastRun && { entity: lastRun, name: "Last run" },
          {
            type: "button",
            name: "Run now",
            icon: "mdi:sprinkler",
            tap_action: {
              action: "call-service",
              service: "rainbird_scheduler.start_zone",
              service_data: { zone: n },
              confirmation: {
                text: `Run ${name} for its configured duration?`,
              },
            },
          },
        ].filter(Boolean),
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

    return {
      title: "Rainbird",
      views: [
        {
          title: "Schedule",
          path: "schedule",
          icon: "mdi:sprinkler-variant",
          cards: [
            headerCard,
            settingsCard,
            weekdaysCard,
            tiles,
            activityCard,
            editorToggleCard,
            editDurationsCard,
            editGpmCard,
            ...zoneCards,
            actionsCard,
          ].filter(Boolean),
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

customElements.define(
  "ll-strategy-rainbird-scheduler",
  RainbirdSchedulerStrategy
);
customElements.define(
  "ll-strategy-dashboard-rainbird-scheduler",
  RainbirdSchedulerDashboardStrategy
);
