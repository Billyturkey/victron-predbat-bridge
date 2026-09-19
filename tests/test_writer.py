"""Tests for adaptive write verification and recovery capture."""

from __future__ import annotations

import types
import unittest

from support import Hass, State, load_bridge_modules


const, _controller, writer = load_bridge_modules()


class WriterTests(unittest.IsolatedAsyncioTestCase):
    async def test_write_uses_explicit_entity_target(self):
        hass = Hass({"number.target": State(50)})
        sent = await writer._write_value(hass, "number.target", 100)
        self.assertTrue(sent)
        self.assertEqual(hass.services.calls[0][4], {"entity_id": "number.target"})

    async def test_different_reported_value_does_not_fail_or_retry(self):
        hass = Hass({"number.target": State(6999)}, update=False)
        sent = await writer._write_value(hass, "number.target", 7399)
        self.assertTrue(sent)
        self.assertEqual(hass.states.get("number.target").state, "6999")
        self.assertEqual(len(hass.services.calls), 1)

    async def test_service_error_is_rejected(self):
        hass = Hass({"number.target": State(50)})

        async def fail(*args, **kwargs):
            raise writer.HomeAssistantError("service failed")

        hass.services.async_call = fail
        self.assertFalse(await writer._write_value(hass, "number.target", 100))

    async def test_baseline_capture_rejects_active_controller(self):
        data = {
            const.CONF_AC_SETPOINT: "number.grid",
            const.CONF_MAX_CHARGE_CURRENT: "number.current",
            const.CONF_MAX_INVERTER_POWER: "number.inverter",
            const.CONF_MIN_SOC: "number.soc",
        }
        hass = Hass({
            "number.grid": State(-1000), "number.current": State(140),
            "number.inverter": State(7399), "number.soc": State(10),
        })
        runtime = types.SimpleNamespace(write_status="", baseline={}, owned=False)
        hass.data = {const.DOMAIN: {"entry": runtime}}
        entry = types.SimpleNamespace(entry_id="entry", data=data)
        self.assertFalse(await writer.async_capture_baseline(hass, entry))
        self.assertFalse(runtime.owned)
        self.assertIn("stop the old controller", runtime.write_status)


if __name__ == "__main__":
    unittest.main()
