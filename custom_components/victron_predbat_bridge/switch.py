"""Enable switch for Victron Predbat Bridge."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, SIGNAL_UPDATE, VERSION


async def async_setup_entry(hass, entry, async_add_entities):
    """Create the bridge switch."""
    async_add_entities([BridgeEnableSwitch(hass, entry), BridgeWriteSwitch(hass, entry)])


class BridgeEnableSwitch(SwitchEntity, RestoreEntity):
    """Enable request processing."""

    _attr_has_entity_name = True
    _attr_name = "Control"

    def __init__(self, hass, entry):
        self._hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_control"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Victron Predbat Bridge",
            "manufacturer": "Community",
            "model": "Predbat service bridge",
            "sw_version": VERSION,
        }

    @property
    def is_on(self):
        return self._hass.data[DOMAIN][self._entry.entry_id].enabled

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        runtime = self._hass.data[DOMAIN][self._entry.entry_id]
        if state is not None:
            runtime.enabled = state.state == "on"
        runtime.status = (
            "Enabled — guarded writes remain locked"
            if runtime.enabled
            else "Disabled — shadow calculations only"
        )
        if runtime.enabled:
            from . import async_recalculate
            from .writer import async_apply_shadow

            async_recalculate(self.hass, self._entry)
            await async_apply_shadow(self.hass, self._entry)
        else:
            async_dispatcher_send(self.hass, SIGNAL_UPDATE)

    async def async_turn_on(self, **kwargs):
        runtime = self._hass.data[DOMAIN][self._entry.entry_id]
        runtime.enabled = True
        from . import async_recalculate

        async_recalculate(self.hass, self._entry)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        runtime = self._hass.data[DOMAIN][self._entry.entry_id]
        if runtime.owned:
            from .writer import async_restore_baseline

            await async_restore_baseline(
                self.hass, self._entry, "bridge Control disabled", disarm=True
            )
        else:
            runtime.armed = False
            await runtime.store.async_save(
                {"owned": False, "armed": False, "baseline": runtime.baseline}
            )
        runtime.enabled = False
        runtime.status = "Disabled — shadow calculations only"
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)
        self.async_write_ha_state()


class BridgeWriteSwitch(SwitchEntity):
    """Deliberate, non-restoring lock for Victron writes."""

    _attr_has_entity_name = True
    _attr_name = "Allow Victron writes"
    _attr_icon = "mdi:shield-lock-open"

    def __init__(self, hass, entry):
        self._hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_allow_writes"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.entry_id)}}

    @property
    def is_on(self):
        return self._hass.data[DOMAIN][self._entry.entry_id].armed

    async def async_added_to_hass(self):
        """Keep the switch synchronized with automatic fail-safe changes."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_UPDATE, self.async_write_ha_state)
        )

    async def async_turn_on(self, **kwargs):
        from .writer import async_apply_shadow, async_enable_writes

        runtime = self._hass.data[DOMAIN][self._entry.entry_id]
        runtime.armed = True
        await runtime.store.async_save(
            {"owned": runtime.owned, "armed": True, "baseline": runtime.baseline}
        )
        if await async_enable_writes(self.hass, self._entry):
            await async_apply_shadow(self.hass, self._entry)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        from .writer import async_restore_baseline

        runtime = self._hass.data[DOMAIN][self._entry.entry_id]
        runtime.armed = False
        await async_restore_baseline(
            self.hass, self._entry, "user disabled writes", disarm=True
        )
        self.async_write_ha_state()
