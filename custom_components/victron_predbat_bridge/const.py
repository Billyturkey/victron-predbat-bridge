"""Constants for Victron Predbat Bridge."""

from homeassistant.const import Platform

DOMAIN = "victron_predbat_bridge"
VERSION = "0.7.0"

PLATFORMS = [Platform.SENSOR, Platform.SWITCH]

CONF_BATTERY_SOC = "battery_soc"
CONF_BATTERY_POWER = "battery_power"
CONF_BATTERY_VOLTAGE = "battery_voltage"
CONF_GRID_POWER = "grid_power"
CONF_LOAD_POWER = "load_power"
CONF_PV_POWER = "pv_power"
CONF_EV_POWER = "ev_power"
CONF_AC_SETPOINT = "ac_setpoint"
CONF_MAX_CHARGE_CURRENT = "max_charge_current"
CONF_MAX_INVERTER_POWER = "max_inverter_power"
CONF_MIN_SOC = "min_soc"

OPT_MAX_CHARGE_POWER = "max_charge_power"
OPT_MAX_EXPORT_POWER = "max_export_power"
OPT_CHARGE_CURRENT_LIMIT = "charge_current_limit"
OPT_NORMAL_INVERTER_LIMIT = "normal_inverter_limit"
OPT_MAX_VICTRON_IMPORT = "max_victron_import"
OPT_SITE_IMPORT_LIMIT = "site_import_limit"
OPT_GRID_EXPORT_LIMIT = "grid_export_limit"
OPT_STANDBY_GRID_TARGET = "standby_grid_target"
OPT_RESERVE_FLOOR = "reserve_floor"
OPT_MIN_BATTERY_VOLTAGE = "min_battery_voltage"
OPT_MAX_BATTERY_VOLTAGE = "max_battery_voltage"
OPT_EFFICIENCY = "conversion_efficiency"
OPT_BATTERY_POSITIVE_CHARGING = "battery_positive_charging"
OPT_GRID_POSITIVE_IMPORT = "grid_positive_import"
OPT_PHASE_COUNT = "phase_count"
OPT_REQUEST_TIMEOUT = "request_timeout"
OPT_WRITES_ACKNOWLEDGED = "writes_acknowledged"
OPT_CONNECTED_ENTITY = "connected_entity"
OPT_ESS_MODE_ENTITY = "ess_mode_entity"
OPT_HUB4_MODE_ENTITY = "hub4_mode_entity"
OPT_DESS_MODE_ENTITY = "dess_mode_entity"
OPT_INVERTER_MODE_ENTITY = "inverter_mode_entity"
OPT_SCHEDULE_0_ENTITY = "schedule_0_entity"
OPT_SCHEDULE_1_ENTITY = "schedule_1_entity"
OPT_SCHEDULE_2_ENTITY = "schedule_2_entity"
OPT_SCHEDULE_3_ENTITY = "schedule_3_entity"
OPT_SCHEDULE_4_ENTITY = "schedule_4_entity"

DEFAULT_OPTIONS = {
    OPT_MAX_CHARGE_POWER: 7000.0,
    OPT_MAX_EXPORT_POWER: 7000.0,
    OPT_CHARGE_CURRENT_LIMIT: 140.0,
    OPT_NORMAL_INVERTER_LIMIT: 7399.0,
    OPT_MAX_VICTRON_IMPORT: 8000.0,
    OPT_SITE_IMPORT_LIMIT: 12000.0,
    OPT_GRID_EXPORT_LIMIT: 7400.0,
    OPT_STANDBY_GRID_TARGET: 50.0,
    OPT_RESERVE_FLOOR: 10.0,
    OPT_MIN_BATTERY_VOLTAGE: 40.0,
    OPT_MAX_BATTERY_VOLTAGE: 60.0,
    OPT_EFFICIENCY: 96.0,
    OPT_BATTERY_POSITIVE_CHARGING: True,
    OPT_GRID_POSITIVE_IMPORT: True,
    OPT_PHASE_COUNT: "1",
    OPT_REQUEST_TIMEOUT: 720.0,
    OPT_WRITES_ACKNOWLEDGED: False,
}

SIGNAL_UPDATE = f"{DOMAIN}_update"
SERVICE_REQUEST = "request"
