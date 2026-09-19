"""Guarded Victron number writes."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_AC_SETPOINT,
    CONF_MAX_CHARGE_CURRENT,
    CONF_MAX_INVERTER_POWER,
    CONF_MIN_SOC,
    DOMAIN,
    OPT_WRITES_ACKNOWLEDGED,
    SIGNAL_UPDATE,
)

WRITE_ORDER = (
    (CONF_MIN_SOC, "minimum_soc"),
    (CONF_MAX_CHARGE_CURRENT, "charge_current"),
    (CONF_MAX_INVERTER_POWER, "inverter_limit"),
    (CONF_AC_SETPOINT, "grid_setpoint"),
)
RESTORE_ORDER = (CONF_AC_SETPOINT, CONF_MAX_CHARGE_CURRENT, CONF_MAX_INVERTER_POWER, CONF_MIN_SOC)


def _numeric_state(hass: HomeAssistant, entity_id: str) -> float | None:
    state = hass.states.get(entity_id)
    if state is None or state.state in ("unknown", "unavailable"):
        return None
    try:
        return float(state.state)
    except (TypeError, ValueError):
        return None


async def _write_value(hass: HomeAssistant, entity_id: str, value: float) -> bool:
    """Send one number command and accept device-side rounding or limiting."""
    try:
        await hass.services.async_call(
            "number",
            "set_value",
            {"value": value},
            blocking=True,
            target={"entity_id": entity_id},
        )
    except HomeAssistantError:
        return False
    return True


async def async_capture_baseline(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Capture recoverable settings only while the grid target is normal."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    baseline = {
        key: _numeric_state(hass, entry.data[key])
        for key in (CONF_AC_SETPOINT, CONF_MAX_CHARGE_CURRENT, CONF_MAX_INVERTER_POWER, CONF_MIN_SOC)
    }
    if any(value is None for value in baseline.values()):
        runtime.write_status = "Writes blocked — a recovery setting is unavailable"
        return False
    if abs(baseline[CONF_AC_SETPOINT]) > 200:
        runtime.write_status = "Writes blocked — stop the old controller and restore its normal grid target"
        return False
    runtime.baseline = baseline
    runtime.owned = True
    await runtime.store.async_save(
        {"owned": True, "armed": runtime.armed, "baseline": baseline}
    )
    return True


async def async_restore_baseline(
    hass: HomeAssistant, entry: ConfigEntry, reason: str, *, disarm: bool = False
) -> bool:
    """Restore every captured setting and retain recovery data on any failure."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    if disarm:
        runtime.armed = False
    # Close the write gate before waiting for the lock. State callbacks already
    # queued behind an in-progress write must then exit without applying again.
    runtime.writes_enabled = False
    if not runtime.owned or not runtime.baseline:
        runtime.writes_enabled = False
        await runtime.store.async_save(
            {"owned": False, "armed": runtime.armed, "baseline": runtime.baseline}
        )
        runtime.write_status = f"Writes {'disarmed' if not runtime.armed else 'waiting'} — {reason}"
        async_dispatcher_send(hass, SIGNAL_UPDATE)
        return True
    async with runtime.write_lock:
        for key in RESTORE_ORDER:
            value = runtime.baseline.get(key)
            sent = value is not None and await _write_value(
                hass, entry.data[key], float(value)
            )
            if not sent:
                runtime.writes_enabled = False
                if disarm:
                    runtime.armed = False
                runtime.write_status = (
                    f"RECOVERY REQUIRED — service call failed for "
                    f"{entry.data[key]} while restoring {value}"
                )
                await runtime.store.async_save(
                    {
                        "owned": True,
                        "armed": runtime.armed,
                        "baseline": runtime.baseline,
                    }
                )
                async_dispatcher_send(hass, SIGNAL_UPDATE)
                return False
        runtime.owned = False
        runtime.writes_enabled = False
        await runtime.store.async_save(
            {"owned": False, "armed": runtime.armed, "baseline": runtime.baseline}
        )
        runtime.write_status = (
            f"Original settings restored — {'waiting for fresh safe request' if runtime.armed else 'writes disarmed'} ({reason})"
        )
        async_dispatcher_send(hass, SIGNAL_UPDATE)
        return True


async def async_enable_writes(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Pass both locks, capture recovery data, then allow guarded writes."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    async with runtime.write_lock:
        if runtime.writes_enabled:
            return True
        if not runtime.armed:
            return False
        if not entry.options.get(OPT_WRITES_ACKNOWLEDGED, False):
            runtime.write_status = "Writes blocked — risk acknowledgement is off in Configure"
            async_dispatcher_send(hass, SIGNAL_UPDATE)
            return False
        if not runtime.enabled:
            runtime.write_status = "Writes blocked — bridge Control is off"
            async_dispatcher_send(hass, SIGNAL_UPDATE)
            return False
        if runtime.shadow is None or not runtime.shadow.safety_ready:
            runtime.write_status = "Writes waiting — safety gate is not valid"
            async_dispatcher_send(hass, SIGNAL_UPDATE)
            return False
        if not await async_capture_baseline(hass, entry):
            async_dispatcher_send(hass, SIGNAL_UPDATE)
            return False
        runtime.writes_enabled = True
        runtime.write_status = "Guarded writes enabled"
        async_dispatcher_send(hass, SIGNAL_UPDATE)
        return True


async def async_apply_shadow(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply a complete command set or fail closed and restore the baseline."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    # An interrupted shutdown may start before Victron entities are available.
    # Keep retrying the stored baseline before considering any new command.
    if runtime.owned and not runtime.writes_enabled:
        if not await async_restore_baseline(hass, entry, "pending recovery retry"):
            return
    if not runtime.writes_enabled:
        if not runtime.armed:
            return
        if not await async_enable_writes(hass, entry):
            return
    if runtime.shadow is None or not runtime.shadow.safety_ready:
        await async_restore_baseline(hass, entry, "safety gate failed")
        return
    async with runtime.write_lock:
        # State-change callbacks raised by our own writes may queue here. Recheck
        # after acquiring the lock so none can reapply a command after restore.
        if not runtime.writes_enabled or not runtime.armed:
            return
        if runtime.shadow is None or not runtime.shadow.safety_ready:
            restore_reason = "safety gate failed"
        else:
            restore_reason = None
        if restore_reason:
            runtime.write_status = "Safety changed — restoring original settings"
            async_dispatcher_send(hass, SIGNAL_UPDATE)
        else:
            for key, attribute in WRITE_ORDER:
                value = float(getattr(runtime.shadow, attribute))
                if not await _write_value(hass, entry.data[key], value):
                    runtime.writes_enabled = False
                    runtime.armed = False
                    runtime.write_status = (
                        f"Write service failed — {entry.data[key]} requested "
                        f"{value}; restoring"
                    )
                    await runtime.store.async_save(
                        {
                            "owned": runtime.owned,
                            "armed": False,
                            "baseline": runtime.baseline,
                        }
                    )
                    async_dispatcher_send(hass, SIGNAL_UPDATE)
                    restore_reason = "write service failure"
                    break
            else:
                runtime.write_status = "Guarded writes active — commands sent"
                async_dispatcher_send(hass, SIGNAL_UPDATE)
                return
    await async_restore_baseline(
        hass,
        entry,
        restore_reason,
        disarm=restore_reason == "write service failure",
    )
