"""Config flow for Victron Predbat Bridge."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import (
    CONF_AC_SETPOINT,
    CONF_BATTERY_POWER,
    CONF_BATTERY_SOC,
    CONF_BATTERY_VOLTAGE,
    CONF_EV_POWER,
    CONF_GRID_POWER,
    CONF_LOAD_POWER,
    CONF_MAX_CHARGE_CURRENT,
    CONF_MAX_INVERTER_POWER,
    CONF_MIN_SOC,
    CONF_PV_POWER,
    DEFAULT_OPTIONS,
    DOMAIN,
    OPT_BATTERY_POSITIVE_CHARGING,
    OPT_CHARGE_CURRENT_LIMIT,
    OPT_CONNECTED_ENTITY,
    OPT_DESS_MODE_ENTITY,
    OPT_EFFICIENCY,
    OPT_GRID_EXPORT_LIMIT,
    OPT_GRID_POSITIVE_IMPORT,
    OPT_HUB4_MODE_ENTITY,
    OPT_INVERTER_MODE_ENTITY,
    OPT_MAX_BATTERY_VOLTAGE,
    OPT_MAX_CHARGE_POWER,
    OPT_MAX_EXPORT_POWER,
    OPT_MAX_VICTRON_IMPORT,
    OPT_MIN_BATTERY_VOLTAGE,
    OPT_NORMAL_INVERTER_LIMIT,
    OPT_ESS_MODE_ENTITY,
    OPT_PHASE_COUNT,
    OPT_RESERVE_FLOOR,
    OPT_REQUEST_TIMEOUT,
    OPT_WRITES_ACKNOWLEDGED,
    OPT_VERIFY_CURRENT_ALLOWANCE,
    OPT_VERIFY_GRID_ALLOWANCE,
    OPT_VERIFY_INVERTER_ALLOWANCE,
    OPT_VERIFY_SOC_ALLOWANCE,
    OPT_SCHEDULE_0_ENTITY,
    OPT_SCHEDULE_1_ENTITY,
    OPT_SCHEDULE_2_ENTITY,
    OPT_SCHEDULE_3_ENTITY,
    OPT_SCHEDULE_4_ENTITY,
    OPT_SITE_IMPORT_LIMIT,
    OPT_STANDBY_GRID_TARGET,
)


def entity(domain: str) -> selector.EntitySelector:
    """Return an entity selector restricted to one domain."""
    return selector.EntitySelector(selector.EntitySelectorConfig(domain=domain))


ENTITY_SUFFIXES = {
    CONF_BATTERY_SOC: ("sensor", "_gx_device_dc_battery_charge"),
    CONF_BATTERY_POWER: ("sensor", "_gx_device_dc_battery_power"),
    CONF_BATTERY_VOLTAGE: ("sensor", "_gx_device_dc_battery_voltage"),
    CONF_GRID_POWER: ("sensor", "_gx_device_grid_power_l1"),
    CONF_LOAD_POWER: ("sensor", "_gx_device_consumption_power_l1"),
    CONF_PV_POWER: ("sensor", "_gx_device_pv_power"),
    CONF_AC_SETPOINT: ("number", "_gx_device_ac_power_setpoint"),
    CONF_MAX_CHARGE_CURRENT: ("number", "_gx_device_ess_max_charge_current"),
    CONF_MAX_INVERTER_POWER: (
        "number",
        "_gx_device_ess_max_inverter_power_limit",
    ),
    CONF_MIN_SOC: ("number", "_gx_device_ess_min_soc_limit"),
}

VICTRON_PLATFORMS = {"victron_gx", "victron_mqtt"}

VICTRON_MQTT_TRANSLATION_KEYS = {
    CONF_BATTERY_SOC: "system_dc_battery_soc",
    CONF_BATTERY_POWER: "system_dc_battery_power",
    CONF_BATTERY_VOLTAGE: "system_dc_battery_voltage",
    CONF_GRID_POWER: "system_grid_power_phase",
    CONF_LOAD_POWER: "system_consumption_power_phase",
    CONF_PV_POWER: "system_dc_pv_power",
    CONF_AC_SETPOINT: "system_ac_power_set_point",
    CONF_MAX_CHARGE_CURRENT: "system_ess_max_charge_current",
    CONF_MAX_INVERTER_POWER: "system_ess_max_inverter_power_limit",
    CONF_MIN_SOC: "system_ess_min_soc_limit",
}


def required_entity(key: str, domain: str, defaults: dict[str, str]):
    """Create a required selector, prefilled when Victron discovery found it."""
    marker = (
        vol.Required(key, default=defaults[key])
        if key in defaults
        else vol.Required(key)
    )
    return marker, entity(domain)


class VictronPredbatBridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure the bridge through the Home Assistant UI."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry):
        """Return the editable system-limits flow."""
        return VictronPredbatBridgeOptionsFlow(config_entry)

    def _discover_victron_entities(self) -> dict[str, str]:
        """Find matching entities owned by the official Victron GX integration."""
        registry = er.async_get(self.hass)
        victron_entries = [
            entry
            for entry in registry.entities.values()
            if entry.platform in VICTRON_PLATFORMS and entry.disabled_by is None
        ]
        discovered = {}
        for key, (domain, suffix) in ENTITY_SUFFIXES.items():
            matches = sorted(
                entry.entity_id
                for entry in victron_entries
                if entry.entity_id.startswith(f"{domain}.")
                and (
                    entry.entity_id.endswith(suffix)
                    or getattr(entry, "translation_key", None)
                    == VICTRON_MQTT_TRANSLATION_KEYS[key]
                )
            )
            if len(matches) == 1:
                discovered[key] = matches[0]
        return discovered

    async def async_step_user(self, user_input=None):
        """Handle initial setup."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(title="Victron Predbat Bridge", data=user_input)

        defaults = self._discover_victron_entities()
        schema = vol.Schema(
            dict(
                [
                    required_entity(CONF_BATTERY_SOC, "sensor", defaults),
                    required_entity(CONF_BATTERY_POWER, "sensor", defaults),
                    required_entity(CONF_BATTERY_VOLTAGE, "sensor", defaults),
                    required_entity(CONF_GRID_POWER, "sensor", defaults),
                    required_entity(CONF_LOAD_POWER, "sensor", defaults),
                    required_entity(CONF_PV_POWER, "sensor", defaults),
                ]
            )
            | {
                vol.Optional(CONF_EV_POWER): entity("sensor"),
            }
            | dict(
                [
                    required_entity(CONF_AC_SETPOINT, "number", defaults),
                    required_entity(CONF_MAX_CHARGE_CURRENT, "number", defaults),
                    required_entity(CONF_MAX_INVERTER_POWER, "number", defaults),
                    required_entity(CONF_MIN_SOC, "number", defaults),
                ]
            )
        )
        return self.async_show_form(step_id="user", data_schema=schema)


class VictronPredbatBridgeOptionsFlow(config_entries.OptionsFlow):
    """Edit installation-specific limits without reinstalling."""

    def __init__(self, config_entry):
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Show and save system limits."""
        if user_input is not None:
            if user_input[OPT_MIN_BATTERY_VOLTAGE] >= user_input[OPT_MAX_BATTERY_VOLTAGE]:
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._schema(user_input),
                    errors={"base": "invalid_voltage_range"},
                )
            return self.async_create_entry(title="", data=user_input)

        current = DEFAULT_OPTIONS | dict(self._config_entry.options)
        return self.async_show_form(step_id="init", data_schema=self._schema(current))

    @staticmethod
    def _schema(values):
        """Build the options form with current values as defaults."""
        number = lambda minimum, maximum, step, unit=None: selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=minimum, max=maximum, step=step, mode="box", unit_of_measurement=unit
            )
        )
        fields = {
                vol.Required(OPT_MAX_CHARGE_POWER, default=values[OPT_MAX_CHARGE_POWER]): number(0, 100000, 50, "W"),
                vol.Required(OPT_MAX_EXPORT_POWER, default=values[OPT_MAX_EXPORT_POWER]): number(0, 100000, 50, "W"),
                vol.Required(OPT_CHARGE_CURRENT_LIMIT, default=values[OPT_CHARGE_CURRENT_LIMIT]): number(0, 2000, 1, "A"),
                vol.Required(OPT_NORMAL_INVERTER_LIMIT, default=values[OPT_NORMAL_INVERTER_LIMIT]): number(0, 100000, 1, "W"),
                vol.Required(OPT_MAX_VICTRON_IMPORT, default=values[OPT_MAX_VICTRON_IMPORT]): number(0, 100000, 50, "W"),
                vol.Required(OPT_SITE_IMPORT_LIMIT, default=values[OPT_SITE_IMPORT_LIMIT]): number(0, 100000, 50, "W"),
                vol.Required(OPT_GRID_EXPORT_LIMIT, default=values[OPT_GRID_EXPORT_LIMIT]): number(0, 100000, 50, "W"),
                vol.Required(OPT_STANDBY_GRID_TARGET, default=values[OPT_STANDBY_GRID_TARGET]): number(-1000, 1000, 10, "W"),
                vol.Required(OPT_RESERVE_FLOOR, default=values[OPT_RESERVE_FLOOR]): number(0, 100, 1, "%"),
                vol.Required(OPT_MIN_BATTERY_VOLTAGE, default=values[OPT_MIN_BATTERY_VOLTAGE]): number(0, 1000, 0.1, "V"),
                vol.Required(OPT_MAX_BATTERY_VOLTAGE, default=values[OPT_MAX_BATTERY_VOLTAGE]): number(0, 1000, 0.1, "V"),
                vol.Required(OPT_EFFICIENCY, default=values[OPT_EFFICIENCY]): number(50, 100, 0.1, "%"),
                vol.Required(OPT_PHASE_COUNT, default=values[OPT_PHASE_COUNT]): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=["1", "3"], mode="dropdown")
                ),
                vol.Required(OPT_BATTERY_POSITIVE_CHARGING, default=values[OPT_BATTERY_POSITIVE_CHARGING]): selector.BooleanSelector(),
                vol.Required(OPT_GRID_POSITIVE_IMPORT, default=values[OPT_GRID_POSITIVE_IMPORT]): selector.BooleanSelector(),
                vol.Required(OPT_REQUEST_TIMEOUT, default=values[OPT_REQUEST_TIMEOUT]): number(60, 3600, 30, "s"),
                vol.Required(OPT_WRITES_ACKNOWLEDGED, default=values[OPT_WRITES_ACKNOWLEDGED]): selector.BooleanSelector(),
                vol.Required(OPT_VERIFY_GRID_ALLOWANCE, default=values[OPT_VERIFY_GRID_ALLOWANCE]): number(0, 5000, 10, "W"),
                vol.Required(OPT_VERIFY_CURRENT_ALLOWANCE, default=values[OPT_VERIFY_CURRENT_ALLOWANCE]): number(0, 100, 1, "A"),
                vol.Required(OPT_VERIFY_INVERTER_ALLOWANCE, default=values[OPT_VERIFY_INVERTER_ALLOWANCE]): number(0, 5000, 10, "W"),
                vol.Required(OPT_VERIFY_SOC_ALLOWANCE, default=values[OPT_VERIFY_SOC_ALLOWANCE]): number(0, 20, 0.1, "%"),
            }
        optional_entities = {
            OPT_CONNECTED_ENTITY: "binary_sensor",
            OPT_ESS_MODE_ENTITY: "select",
            OPT_HUB4_MODE_ENTITY: "select",
            OPT_DESS_MODE_ENTITY: "select",
            OPT_INVERTER_MODE_ENTITY: "select",
            OPT_SCHEDULE_0_ENTITY: "select",
            OPT_SCHEDULE_1_ENTITY: "select",
            OPT_SCHEDULE_2_ENTITY: "select",
            OPT_SCHEDULE_3_ENTITY: "select",
            OPT_SCHEDULE_4_ENTITY: "select",
        }
        for key, domain in optional_entities.items():
            marker = (
                vol.Optional(key, default=values[key])
                if values.get(key)
                else vol.Optional(key)
            )
            fields[marker] = entity(domain)
        return vol.Schema(fields)
