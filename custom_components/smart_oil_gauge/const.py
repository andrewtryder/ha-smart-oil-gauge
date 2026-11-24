"""Constants for the Smart Oil Gauge integration."""

DOMAIN = "smart_oil_gauge"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
CONF_UPDATE_INTERVAL_HOURS = "update_interval_hours"
DEFAULT_UPDATE_INTERVAL_HOURS = 6
# Experimental, opt-in history features. Both write to the Home Assistant
# recorder, and the state backfill uses recorder internals, so they are off
# unless the user turns them on in the options.
CONF_BACKFILL_STATES = "backfill_states"
DEFAULT_BACKFILL_STATES = False
CONF_IMPORT_HISTORY = "import_history"
DEFAULT_IMPORT_HISTORY = False
# Experimental, opt-in sync timing: follow the gauge's own upload schedule
# (read from the portal's Sensor Config page) instead of a fixed interval.
CONF_SCHEDULE_MODE = "schedule_mode"
SCHEDULE_GAUGE = "gauge"
SCHEDULE_FIXED = "fixed"
DEFAULT_SCHEDULE_MODE = SCHEDULE_FIXED
# Experimental, opt-in: let Home Assistant change the gauge's upload interval
# on the portal. Off by default because it submits the portal's form.
CONF_ALLOW_INTERVAL_CHANGE = "allow_interval_change"
DEFAULT_ALLOW_INTERVAL_CHANGE = False
