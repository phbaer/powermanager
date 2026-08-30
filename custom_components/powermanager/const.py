"""Constants for the PowerManager integration."""

DOMAIN = "powermanager"
NAME = "PowerManager"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_UNIT_ID = "unit_id"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_GRID_POWER_ENTITY = "grid_power_entity"
CONF_PV_POWER_ENTITY = "pv_power_entity"
CONF_LOAD_POWER_ENTITY = "load_power_entity"

DEFAULT_PORT = 502
DEFAULT_UNIT_ID = 3
DEFAULT_SCAN_INTERVAL_SECONDS = 30
MIN_SCAN_INTERVAL_SECONDS = 5
MAX_SCAN_INTERVAL_SECONDS = 300
