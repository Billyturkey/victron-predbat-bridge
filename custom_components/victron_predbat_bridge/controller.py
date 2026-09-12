"""Read-only shadow calculations for Victron Predbat Bridge."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    CONF_AC_SETPOINT,
    CONF_BATTERY_SOC,
    CONF_BATTERY_VOLTAGE,
    CONF_EV_POWER,
    CONF_LOAD_POWER,
    CONF_MAX_CHARGE_CURRENT,
    CONF_MAX_INVERTER_POWER,
    CONF_MIN_SOC,
    CONF_PV_POWER,
    DEFAULT_OPTIONS,
    OPT_CHARGE_CURRENT_LIMIT,
    OPT_CONNECTED_ENTITY,
    OPT_DESS_MODE_ENTITY,
    OPT_EFFICIENCY,
    OPT_GRID_EXPORT_LIMIT,
    OPT_HUB4_MODE_ENTITY,
    OPT_INVERTER_MODE_ENTITY,
    OPT_MAX_BATTERY_VOLTAGE,
    OPT_MAX_CHARGE_POWER,
    OPT_MAX_EXPORT_POWER,
    OPT_MAX_VICTRON_IMPORT,
    OPT_MIN_BATTERY_VOLTAGE,
    OPT_NORMAL_INVERTER_LIMIT,
    OPT_ESS_MODE_ENTITY,
    OPT_RESERVE_FLOOR,
    OPT_REQUEST_TIMEOUT,
    OPT_SCHEDULE_0_ENTITY,
    OPT_SCHEDULE_1_ENTITY,
    OPT_SCHEDULE_2_ENTITY,
    OPT_SCHEDULE_3_ENTITY,
    OPT_SCHEDULE_4_ENTITY,
    OPT_SITE_IMPORT_LIMIT,
    OPT_STANDBY_GRID_TARGET,
)


@dataclass
class ShadowResult:
    """Commands calculated by shadow mode; never written to Victron."""

    intent: str = "standby"
    grid_setpoint: float = 50.0
    charge_current: float = 0.0
    inverter_limit: float = 0.0
    minimum_soc: float = 10.0
    source_valid: bool = False
    controls_available: bool = False
    request_fresh: bool = False
    native_ready: bool = False
    safety_ready: bool = False
    safety_note: str = "Safety checks have not run"
    note: str = "Waiting for valid source data"


def _number(hass: HomeAssistant, entity_id: str | None) -> float | None:
    """Return a finite numeric state, or None."""
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None or state.state in ("unknown", "unavailable"):
        return None
    try:
        value = float(state.state)
    except (TypeError, ValueError):
        return None
    return value if value == value and value not in (float("inf"), float("-inf")) else None


def _entity_clamp(hass: HomeAssistant, entity_id: str, value: float) -> float:
    """Clamp a shadow command to the selected number entity's advertised range."""
    state = hass.states.get(entity_id)
    if state is None:
        return value
    try:
        minimum = float(state.attributes.get("min", value))
        maximum = float(state.attributes.get("max", value))
    except (TypeError, ValueError):
        return value
    return min(max(value, minimum), maximum)


def _native_ready(hass: HomeAssistant, settings: dict) -> tuple[bool, str]:
    """Check the native Victron state that must be safe before future writes."""
    keys = (
        OPT_CONNECTED_ENTITY,
        OPT_ESS_MODE_ENTITY,
        OPT_HUB4_MODE_ENTITY,
        OPT_DESS_MODE_ENTITY,
        OPT_INVERTER_MODE_ENTITY,
        OPT_SCHEDULE_0_ENTITY,
        OPT_SCHEDULE_1_ENTITY,
        OPT_SCHEDULE_2_ENTITY,
        OPT_SCHEDULE_3_ENTITY,
        OPT_SCHEDULE_4_ENTITY,
    )
    if any(not settings.get(key) for key in keys):
        return False, "Configure all native ESS safety entities"
    states = {key: hass.states.get(settings[key]) for key in keys}
    if any(state is None or state.state in ("unknown", "unavailable") for state in states.values()):
        return False, "A native ESS safety entity is unavailable"
    if states[OPT_CONNECTED_ENTITY].state != "on":
        return False, "Parallel inverter system is not connected"
    if states[OPT_DESS_MODE_ENTITY].state != "off":
        return False, "Victron Dynamic ESS must be off"
    if states[OPT_INVERTER_MODE_ENTITY].state != "on":
        return False, "Inverter/charger must be on"
    if states[OPT_ESS_MODE_ENTITY].state not in ("optimized_battery_life", "optimized_no_battery_life"):
        return False, "ESS must be in an optimized mode"
    if states[OPT_HUB4_MODE_ENTITY].state not in ("phase_compensation_enabled", "phase_compensation_disabled"):
        return False, "Hub4 ESS mode is not ready"
    schedule_keys = keys[5:]
    if any(not states[key].state.startswith("disabled_") for key in schedule_keys):
        return False, "All five native charge schedules must be disabled"
    return True, "Native ESS state ready"


def calculate_shadow(hass: HomeAssistant, config: dict, options: dict, runtime) -> ShadowResult:
    """Calculate the command set used by the proven YAML controller."""
    settings = DEFAULT_OPTIONS | dict(options)
    max_charge_power = float(settings[OPT_MAX_CHARGE_POWER])
    max_export_power = float(settings[OPT_MAX_EXPORT_POWER])
    max_charge_current = float(settings[OPT_CHARGE_CURRENT_LIMIT])
    normal_inverter_limit = float(settings[OPT_NORMAL_INVERTER_LIMIT])
    max_victron_import = float(settings[OPT_MAX_VICTRON_IMPORT])
    site_import_limit = float(settings[OPT_SITE_IMPORT_LIMIT])
    grid_export_limit = float(settings[OPT_GRID_EXPORT_LIMIT])
    standby_grid_target = float(settings[OPT_STANDBY_GRID_TARGET])
    min_battery_voltage = float(settings[OPT_MIN_BATTERY_VOLTAGE])
    max_battery_voltage = float(settings[OPT_MAX_BATTERY_VOLTAGE])
    efficiency = float(settings[OPT_EFFICIENCY]) / 100.0
    controls_available = all(
        _number(hass, config[key]) is not None
        for key in (CONF_AC_SETPOINT, CONF_MAX_CHARGE_CURRENT, CONF_MAX_INVERTER_POWER, CONF_MIN_SOC)
    )
    native_ready, native_note = _native_ready(hass, settings)
    request_fresh = bool(
        runtime.last_request
        and 0 <= (dt_util.utcnow() - runtime.last_request).total_seconds() <= float(settings[OPT_REQUEST_TIMEOUT])
    )
    soc = _number(hass, config[CONF_BATTERY_SOC])
    volts = _number(hass, config[CONF_BATTERY_VOLTAGE])
    pv = _number(hass, config[CONF_PV_POWER])
    load = _number(hass, config[CONF_LOAD_POWER])
    reserve = _number(hass, config[CONF_MIN_SOC])
    ev = _number(hass, config.get(CONF_EV_POWER)) if config.get(CONF_EV_POWER) else 0.0

    if None in (soc, volts, pv, load, reserve, ev):
        return ShadowResult(
            controls_available=controls_available,
            request_fresh=request_fresh,
            native_ready=native_ready,
            safety_note="A selected source is unavailable",
            note="Shadow stopped — a selected source is unavailable",
        )
    if not 0 <= soc <= 100 or not min_battery_voltage <= volts <= max_battery_voltage:
        return ShadowResult(
            source_valid=False,
            controls_available=controls_available,
            request_fresh=request_fresh,
            native_ready=native_ready,
            safety_note="SOC or battery voltage is outside its valid range",
            note="Shadow stopped — SOC or battery voltage is outside its valid range",
        )

    pv = max(pv, 0.0)
    load = max(load, 0.0)
    ev = max(ev, 0.0)
    reserve = min(max(reserve, float(settings[OPT_RESERVE_FLOOR])), 95.0)

    if not request_fresh:
        intent = "standby"
    elif runtime.charge_request == "charge" and runtime.export_request == "export":
        intent = "standby"
    elif runtime.charge_request == "charge":
        intent = "charge"
    elif runtime.export_request == "export":
        intent = "export"
    elif runtime.charge_request == "preserve":
        intent = "preserve"
    else:
        intent = "demand"

    target = runtime.charge_target if intent == "charge" else max(reserve, runtime.export_target)
    power_limit = max_charge_power if intent == "charge" else max_export_power
    power = min(max(runtime.charge_power if intent == "charge" else runtime.export_power, 0.0), power_limit)
    reached = (intent == "charge" and soc >= target) or (intent == "export" and soc <= target)
    effective = "preserve" if reached or (intent == "export" and ev > 100) else intent
    if effective in ("charge", "export") and power < 100:
        effective = "preserve"

    if effective == "preserve":
        native_reserve = ceil(max(soc, reserve) / 5) * 5
    elif effective == "export":
        native_reserve = ceil(max(target, reserve) / 5) * 5
    else:
        native_reserve = reserve
    native_reserve = min(native_reserve, 100.0)

    grid_command = standby_grid_target
    current_command = max_charge_current
    inverter_command = normal_inverter_limit
    note_parts = []

    if effective == "charge":
        battery_goal = min(max(power, pv - load / efficiency), max_charge_current * volts)
        charge_grid = (
            load + (battery_goal - pv) / efficiency
            if battery_goal >= pv
            else load - (pv - battery_goal) * efficiency
        )
        import_cap = max(site_import_limit - ev, 0.0)
        grid_command = floor(min(max(charge_grid, 0.0), max_victron_import, import_cap) / 10) * 10
        current_command = min(max(ceil(battery_goal / volts), 1), max_charge_current)
        if charge_grid > import_cap:
            note_parts.append("EV/import limited")
    elif effective == "export":
        export_power = max(min(power, max_export_power) - load, 0.0)
        grid_command = -min(ceil(export_power / 10) * 10, grid_export_limit)
        inverter_command = max(floor(power / 50) * 50 - 1, 49)

    grid_command = _entity_clamp(hass, config[CONF_AC_SETPOINT], grid_command)
    current_command = _entity_clamp(hass, config[CONF_MAX_CHARGE_CURRENT], current_command)
    inverter_command = _entity_clamp(hass, config[CONF_MAX_INVERTER_POWER], inverter_command)
    native_reserve = _entity_clamp(hass, config[CONF_MIN_SOC], native_reserve)

    if reached:
        note_parts.append("target reached")
    if intent == "export" and ev > 100:
        note_parts.append("EV export blocked")

    note = f"{effective.title()} | {int(grid_command)} W grid target | {int(current_command)} A charge limit"
    if note_parts:
        note += " | " + " | ".join(note_parts)

    safety_ready = controls_available and native_ready and request_fresh
    if not controls_available:
        safety_note = "A selected Victron control is unavailable"
    elif not native_ready:
        safety_note = native_note
    elif not request_fresh:
        safety_note = "Predbat request is missing or stale"
    else:
        safety_note = "All read-only safety checks passed"

    return ShadowResult(
        intent=effective,
        grid_setpoint=grid_command,
        charge_current=current_command,
        inverter_limit=inverter_command,
        minimum_soc=native_reserve,
        source_valid=True,
        controls_available=controls_available,
        request_fresh=request_fresh,
        native_ready=native_ready,
        safety_ready=safety_ready,
        safety_note=safety_note,
        note=note,
    )
