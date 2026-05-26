"""Constants for the Rain Bird Scheduler integration."""

DOMAIN = "rainbird_scheduler"

# Source integration we orchestrate on top of
RAINBIRD_DOMAIN = "rainbird"

# Optional: Flume integration's daily-total sensor used for GPM calibration.
# Configurable via options flow; falls back to None if Flume isn't installed.
DEFAULT_FLUME_DAILY_SENSOR = "sensor.flume_sensor_home_current_day"

# Settle delay after a zone finishes so Flume's per-minute polling captures
# the trailing 30-60s of flow. Without this, measured GPM is consistently low.
ZONE_SETTLE_MINUTES = 1

# Test-cycle duration per zone (1 min = sample where gallons == gpm).
TEST_CYCLE_MINUTES_PER_ZONE = 1

# Maximum supported zones (Rain Bird ESP-Me / LXMe go up to 22).
MAX_ZONES = 22

# Day-class options for the eligibility schedule.
DAY_CLASS_EVEN = "even"
DAY_CLASS_ODD = "odd"
DAY_CLASS_ALL = "all"
DAY_CLASS_DAY_OF_WEEK = "day of week"
DAY_CLASSES = [DAY_CLASS_EVEN, DAY_CLASS_ODD, DAY_CLASS_ALL, DAY_CLASS_DAY_OF_WEEK]

# Verdict strings (must match v1.0.0 YAML package for log-message continuity).
VERDICT_YES = "yes"
VERDICT_DISABLED = "disabled"
VERDICT_SKIP_WINDOW = "skip-window"
VERDICT_SKIP_MANUAL = "skip-manual"
VERDICT_SKIP_RAIN = "skip-rain"
VERDICT_SKIP_DELAY = "skip-delay"

# Config entry keys
CONF_FLUME_SENSOR = "flume_daily_sensor"
CONF_RAINSENSOR = "rainsensor"
CONF_RAIN_DELAY_SENSOR = "rain_delay_sensor"
CONF_RAIN_DELAY_NUMBER = "rain_delay_number"

# Default daily start time
DEFAULT_START_TIME = "00:00:00"

# Storage / dispatcher signal names
SIGNAL_VERDICT_UPDATED = f"{DOMAIN}_verdict_updated"
SIGNAL_ZONE_RAN = f"{DOMAIN}_zone_ran"
