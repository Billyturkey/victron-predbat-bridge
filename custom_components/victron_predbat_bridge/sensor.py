"""Read-only status and shadow command sensors."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import PERCENTAGE, UnitOfElectricCurrent, UnitOfPower
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN, SIGNAL_UPDATE, VERSION


@dataclass(frozen=True)
class ShadowSensorDescription:
    """Description of one runtime value."""

    key: str
    name: str
    unit: str | None = None
    device_class: SensorDeviceClass | None = None
    category: EntityCategory | None = None


DESCRIPTIONS = (
    # Day-to-day controller state.
    ShadowSensorDescription("status", "Controller status"),
    ShadowSensorDescription("write_status", "Write status"),
    ShadowSensorDescription("armed", "Writes armed"),
    ShadowSensorDescription("writes_enabled", "Writes active"),
    ShadowSensorDescription("owned", "Settings ownership"),
    # Commands the controller has calculated.
    ShadowSensorDescription("intent", "Shadow intent"),
    ShadowSensorDescription("grid_setpoint", "Shadow grid setpoint", UnitOfPower.WATT, SensorDeviceClass.POWER),
    ShadowSensorDescription("charge_current", "Shadow maximum charge current", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT),
    ShadowSensorDescription("inverter_limit", "Shadow inverter limit", UnitOfPower.WATT, SensorDeviceClass.POWER),
    ShadowSensorDescription("minimum_soc", "Shadow minimum SOC", PERCENTAGE, SensorDeviceClass.BATTERY),
    # Detailed checks are shown separately as diagnostics by Home Assistant.
    ShadowSensorDescription("safety_note", "Safety check", category=EntityCategory.DIAGNOSTIC),
    ShadowSensorDescription("safety_ready", "Safety gate", category=EntityCategory.DIAGNOSTIC),
    ShadowSensorDescription("source_valid", "Source sensors", category=EntityCategory.DIAGNOSTIC),
    ShadowSensorDescription("controls_available", "Victron controls", category=EntityCategory.DIAGNOSTIC),
    ShadowSensorDescription("native_ready", "Native ESS state", category=EntityCategory.DIAGNOSTIC),
    ShadowSensorDescription("request_fresh", "Predbat request freshness", category=EntityCategory.DIAGNOSTIC),
    ShadowSensorDescription("last_request", "Last Predbat request", device_class=SensorDeviceClass.TIMESTAMP, category=EntityCategory.DIAGNOSTIC),
)


async def async_setup_entry(hass, entry, async_add_entities):
    """Create the bridge status and planned-command sensors."""
    async_add_entities(
        [BridgeShadowSensor(hass, entry, description) for description in DESCRIPTIONS]
    )


class BridgeShadowSensor(SensorEntity):
    """Expose one bridge runtime value without controlling Victron."""

    _attr_has_entity_name = True

    def __init__(self, hass, entry, description: ShadowSensorDescription):
        self._hass = hass
        self._entry = entry
        self._description = description
        self._attr_name = description.name
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_native_unit_of_measurement = description.unit
        self._attr_device_class = description.device_class
        self._attr_entity_category = description.category
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Victron Predbat Bridge",
            "manufacturer": "Community",
            "model": "Predbat service bridge",
            "sw_version": VERSION,
        }

    @property
    def native_value(self):
        """Return the current runtime or shadow value."""
        runtime = self._hass.data[DOMAIN][self._entry.entry_id]
        if self._description.key == "status":
            return runtime.status
        if self._description.key == "write_status":
            return runtime.write_status
        if self._description.key == "writes_enabled":
            return "active" if runtime.writes_enabled else "locked"
        if self._description.key == "armed":
            return "armed" if runtime.armed else "disarmed"
        if self._description.key == "owned":
            return "owned" if runtime.owned else "released"
        if self._description.key == "last_request":
            return runtime.last_request
        shadow = runtime.shadow
        if shadow is None:
            return None
        value = getattr(shadow, self._description.key)
        if self._description.key in (
            "source_valid",
            "controls_available",
            "request_fresh",
            "native_ready",
            "safety_ready",
        ):
            return "valid" if value else "invalid"
        return value

    async def async_added_to_hass(self):
        """Subscribe to runtime changes."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_UPDATE, self.async_write_ha_state)
        )
