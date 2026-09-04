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
CONF_TELEMETRY_MAX_AGE = "telemetry_max_age"
CONF_PRICE_ENTITY = "price_entity"
CONF_REMAINING_PV_FORECAST_ENTITY = "remaining_pv_forecast_entity"
CONF_REMAINING_LOAD_FORECAST_ENTITY = "remaining_load_forecast_entity"

DEFAULT_PORT = 502
DEFAULT_UNIT_ID = 3
DEFAULT_SCAN_INTERVAL_SECONDS = 30
MIN_SCAN_INTERVAL_SECONDS = 5
MAX_SCAN_INTERVAL_SECONDS = 300
DEFAULT_TELEMETRY_MAX_AGE_SECONDS = 120
MIN_TELEMETRY_MAX_AGE_SECONDS = 10
MAX_TELEMETRY_MAX_AGE_SECONDS = 3600
