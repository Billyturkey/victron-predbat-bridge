"""Victron Predbat Bridge integration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BATTERY_POWER,
    CONF_BATTERY_SOC,
    CONF_BATTERY_VOLTAGE,
    CONF_EV_POWER,
    CONF_GRID_POWER,
    CONF_LOAD_POWER,
    CONF_MIN_SOC,
    CONF_PV_POWER,
    DOMAIN,
    PLATFORMS,
    SERVICE_REQUEST,
    SIGNAL_UPDATE,
    VERSION,
    OPT_CONNECTED_ENTITY,
    OPT_DESS_MODE_ENTITY,
    OPT_ESS_MODE_ENTITY,
    OPT_HUB4_MODE_ENTITY,
    OPT_INVERTER_MODE_ENTITY,
    OPT_WRITES_ACKNOWLEDGED,
    OPT_SCHEDULE_0_ENTITY,
    OPT_SCHEDULE_1_ENTITY,
    OPT_SCHEDULE_2_ENTITY,
    OPT_SCHEDULE_3_ENTITY,
    OPT_SCHEDULE_4_ENTITY,
)
from .controller import ShadowResult, calculate_shadow


@dataclass
class BridgeRuntime:
    """Runtime state for shadow calculation and guarded writes."""

    enabled: bool = False
    status: str = "Disabled — shadow calculations only"
    charge_request: str = "off"
    export_request: str = "off"
    charge_target: float = 100.0
    export_target: float = 10.0
    charge_power: float = 0.0
    export_power: float = 0.0
    last_request: datetime | None = None
    shadow: ShadowResult | None = None
    writes_enabled: bool = False
    armed: bool = False
    owned: bool = False
    baseline: dict = field(default_factory=dict)
    write_status: str = "Writes locked off"
    write_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    store: Store | None = None
    remove_listeners: list = field(default_factory=list)


def async_recalculate(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Refresh all shadow command entities without writing to Victron."""
    runtime: BridgeRuntime = hass.data[DOMAIN][entry.entry_id]
    runtime.shadow = calculate_shadow(hass, entry.data, entry.options, runtime)
    if not runtime.enabled:
        runtime.status = "Disabled — shadow calculations only"
    elif not runtime.shadow.source_valid:
        runtime.status = runtime.shadow.note
    else:
        suffix = "guarded writes active" if runtime.writes_enabled else "writes locked"
        runtime.status = f"{runtime.shadow.intent.title()} — {suffix}"
    async_dispatcher_send(hass, SIGNAL_UPDATE)


REQUEST_SCHEMA = vol.Schema(
    {
        vol.Required("direction"): vol.In(("charge", "export")),
        vol.Required("request"): vol.In(("off", "charge", "export", "preserve")),
        vol.Optional("target_soc"): vol.Coerce(float),
        vol.Optional("power"): vol.Coerce(float),
    }
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the Predbat request service."""

    async def handle_request(call: ServiceCall) -> None:
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            return
        runtime: BridgeRuntime = hass.data[DOMAIN][entries[0].entry_id]
        entry = entries[0]
        direction = call.data["direction"]
        request = call.data["request"]
        if direction == "charge":
            runtime.charge_request = request if request in ("off", "charge", "preserve") else "off"
            if request != "off":
                runtime.charge_target = min(max(call.data.get("target_soc", 100.0), 0.0), 100.0)
                runtime.charge_power = max(call.data.get("power", runtime.charge_power), 0.0)
        else:
            runtime.export_request = "export" if request == "export" else "off"
            if request != "off":
                runtime.export_target = min(max(call.data.get("target_soc", 10.0), 0.0), 100.0)
                runtime.export_power = max(call.data.get("power", runtime.export_power), 0.0)
        runtime.last_request = dt_util.utcnow()
        async_recalculate(hass, entry)
        from .writer import async_apply_shadow

        await async_apply_shadow(hass, entry)

    hass.services.async_register(
        DOMAIN, SERVICE_REQUEST, handle_request, schema=REQUEST_SCHEMA
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a configured bridge."""
    runtime = BridgeRuntime()
    runtime.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
    saved = await runtime.store.async_load() or {}
    runtime.owned = bool(saved.get("owned", False))
    runtime.armed = bool(saved.get("armed", False))
    runtime.baseline = saved.get("baseline", {})
    if not entry.options.get(OPT_WRITES_ACKNOWLEDGED, False):
        runtime.armed = False
        await runtime.store.async_save(
            {"owned": runtime.owned, "armed": False, "baseline": runtime.baseline}
        )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer="Community",
        model="Predbat service bridge",
        name="Victron Predbat Bridge",
        sw_version=VERSION,
    )
    watched_entities = [
        entry.data[key]
        for key in (
            CONF_BATTERY_SOC,
            CONF_BATTERY_POWER,
            CONF_BATTERY_VOLTAGE,
            CONF_GRID_POWER,
            CONF_LOAD_POWER,
            CONF_PV_POWER,
            CONF_MIN_SOC,
        )
    ]
    if entry.data.get(CONF_EV_POWER):
        watched_entities.append(entry.data[CONF_EV_POWER])
    for key in (
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
    ):
        if entry.options.get(key):
            watched_entities.append(entry.options[key])

    async def source_changed(event=None) -> None:
        async_recalculate(hass, entry)
        runtime: BridgeRuntime = hass.data[DOMAIN][entry.entry_id]
        # Source telemetry may update several times per second. Recalculate the
        # plan for display without writing every small adjustment. Safety
        # failures still restore the captured settings immediately.
        if runtime.writes_enabled and (
            runtime.shadow is None or not runtime.shadow.safety_ready
        ):
            from .writer import async_restore_baseline

            await async_restore_baseline(hass, entry, "safety gate failed")

    async def periodic_update(now=None) -> None:
        async_recalculate(hass, entry)
        from .writer import async_apply_shadow

        await async_apply_shadow(hass, entry)

    runtime.remove_listeners.append(
        async_track_state_change_event(hass, watched_entities, source_changed)
    )
    runtime.remove_listeners.append(
        async_track_time_interval(hass, periodic_update, timedelta(seconds=30))
    )
    async_recalculate(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    if runtime.owned:
        from .writer import async_restore_baseline

        await async_restore_baseline(hass, entry, "restart recovery")
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload immediately after the user saves new system limits."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the bridge."""
    runtime: BridgeRuntime = hass.data[DOMAIN][entry.entry_id]
    if runtime.owned:
        from .writer import async_restore_baseline

        await async_restore_baseline(hass, entry, "integration unloaded")
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        runtime = hass.data[DOMAIN].pop(entry.entry_id)
        for remove_listener in runtime.remove_listeners:
            remove_listener()
    return unload_ok
