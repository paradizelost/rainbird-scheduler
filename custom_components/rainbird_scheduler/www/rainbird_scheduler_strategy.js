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

    // Find rainbird_scheduler entities by matching the integration's domain
    // pattern in unique_id slugs: anything with rainbird_scheduler in id.
    const isOurs = (id) => id.includes("rainbird_scheduler_");

    const zoneNums = Object.keys(states)
      .filter((id) => id.startsWith("number.") && isOurs(id) && id.endsWith("_minutes"))
      .map((id) => {
        const m = id.match(/_zone_(\d+)_minutes$/);
        return m ? parseInt(m[1], 10) : null;
      })
      .filter((n) => n !== null)
      .sort((a, b) => a - b);

    const idFor = (suffix) =>
      Object.keys(states).find(
        (id) => isOurs(id) && id.endsWith(`_${suffix}`)
      );

    const zoneEntity = (n, kind) =>
      Object.keys(states).find(
        (id) => isOurs(id) && id.endsWith(`_zone_${n}_${kind}`)
      );

    const zoneName = (n) => {
      const eid = zoneEntity(n, "minutes");
      if (!eid) return `Zone ${n}`;
      const fn = states[eid]?.attributes?.friendly_name || "";
      // Strip the " Minutes" suffix our entity adds
      return fn.replace(/\s+Minutes$/, "");
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

    // ---- Zone cards
    const zoneCards = zoneNums.map((n) => {
      const minutes = zoneEntity(n, "minutes");
      const gpm = zoneEntity(n, "gpm");
      const lastRun = zoneEntity(n, "last_run");
      const name = zoneName(n);
      return {
        type: "entities",
        title: name,
        show_header_toggle: false,
        entities: [
          minutes && { entity: minutes, name: "Runtime" },
          gpm && { entity: gpm, name: "Flow rate" },
          lastRun && { entity: lastRun, name: "Last run" },
          {
            type: "button",
            name: "Run now",
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
            ...zoneCards,
            actionsCard,
          ].filter(Boolean),
        },
      ],
    };
  }
}

customElements.define(
  "ll-strategy-rainbird-scheduler",
  RainbirdSchedulerStrategy
);
// Also register the dashboard-level variant some HA versions prefer
customElements.define(
  "ll-strategy-dashboard-rainbird-scheduler",
  RainbirdSchedulerStrategy
);
