"""Guarded and verified Victron number writes."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_AC_SETPOINT,
    CONF_MAX_CHARGE_CURRENT,
    CONF_MAX_INVERTER_POWER,
    CONF_MIN_SOC,
    DEFAULT_OPTIONS,
    DOMAIN,
    OPT_VERIFY_CURRENT_ALLOWANCE,
    OPT_VERIFY_GRID_ALLOWANCE,
    OPT_VERIFY_INVERTER_ALLOWANCE,
    OPT_VERIFY_SOC_ALLOWANCE,
    OPT_WRITES_ACKNOWLEDGED,
    SIGNAL_UPDATE,
)

WRITE_ORDER = (
    (CONF_MIN_SOC, "minimum_soc", OPT_VERIFY_SOC_ALLOWANCE),
    (CONF_MAX_CHARGE_CURRENT, "charge_current", OPT_VERIFY_CURRENT_ALLOWANCE),
    (CONF_MAX_INVERTER_POWER, "inverter_limit", OPT_VERIFY_INVERTER_ALLOWANCE),
    (CONF_AC_SETPOINT, "grid_setpoint", OPT_VERIFY_GRID_ALLOWANCE),
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


async def _write_and_verify(
    hass: HomeAssistant,
    entity_id: str,
    value: float,
    configured_allowance: float,
    latest_value: Callable[[], float] | None = None,
) -> tuple[bool, float | None, float]:
    """Write, follow a moving target, retry once, and verify entity feedback."""
    state = hass.states.get(entity_id)
    try:
        entity_step = abs(float(state.attributes.get("step", 0))) if state else 0.0
    except (TypeError, ValueError):
        entity_step = 0.0
    allowance = max(float(configured_allowance), entity_step)
    desired = value
    reported = _numeric_state(hass, entity_id)

    for attempt in range(2):
        latest = float(latest_value()) if latest_value is not None else desired
        if reported is None:
            return False, None, latest
        if min(abs(reported - desired), abs(reported - latest)) <= allowance:
            return True, reported, latest
        # The second attempt follows the newest calculation rather than
        # replaying a target made stale by changing load or battery voltage.
        if attempt:
            desired = latest
        try:
            await hass.services.async_call(
                "number",
                "set_value",
                {"value": desired},
                blocking=True,
                target={"entity_id": entity_id},
            )
        except HomeAssistantError:
            return False, _numeric_state(hass, entity_id), latest
        for _ in range(40):
            await asyncio.sleep(0.25)
            reported = _numeric_state(hass, entity_id)
            latest = float(latest_value()) if latest_value is not None else desired
            if reported is not None and min(
                abs(reported - desired), abs(reported - latest)
            ) <= allowance:
                return True, reported, latest
    return False, reported, latest


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
            confirmed, reported, _latest = (
                (False, None, float(value or 0.0))
                if value is None
                else await _write_and_verify(
                    hass, entry.data[key], float(value), 0.0
                )
            )
            if not confirmed:
                runtime.writes_enabled = False
                if disarm:
                    runtime.armed = False
                runtime.write_status = (
                    f"RECOVERY REQUIRED — {entry.data[key]} requested "
                    f"{value}, reported {reported}"
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
            settings = DEFAULT_OPTIONS | dict(entry.options)
            for key, attribute, allowance_key in WRITE_ORDER:
                value = float(getattr(runtime.shadow, attribute))
                confirmed, reported, latest = await _write_and_verify(
                    hass,
                    entry.data[key],
                    value,
                    float(settings[allowance_key]),
                    lambda attribute=attribute: float(
                        getattr(runtime.shadow, attribute)
                    ),
                )
                if not confirmed:
                    runtime.writes_enabled = False
                    runtime.armed = False
                    runtime.write_status = (
                        f"Write failed — {entry.data[key]} requested "
                        f"{value}, latest {latest}, reported {reported}; restoring"
                    )
                    await runtime.store.async_save(
                        {
                            "owned": runtime.owned,
                            "armed": False,
                            "baseline": runtime.baseline,
                        }
                    )
                    async_dispatcher_send(hass, SIGNAL_UPDATE)
                    restore_reason = "write/readback failure"
                    break
            else:
                runtime.write_status = "Guarded writes active — all settings confirmed"
                async_dispatcher_send(hass, SIGNAL_UPDATE)
                return
    await async_restore_baseline(
        hass,
        entry,
        restore_reason,
        disarm=restore_reason == "write/readback failure",
    )
