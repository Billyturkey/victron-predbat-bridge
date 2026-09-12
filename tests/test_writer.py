"""Tests for adaptive write verification and recovery capture."""

from __future__ import annotations

import asyncio
import types
import unittest

from support import Hass, State, load_bridge_modules


const, _controller, writer = load_bridge_modules()


class WriterTests(unittest.IsolatedAsyncioTestCase):
    async def test_entity_step_is_used_as_allowance(self):
        hass = Hass({"number.target": State(99, {"step": 1})})
        confirmed, reported, latest = await writer._write_and_verify(
            hass, "number.target", 100, 0
        )
        self.assertTrue(confirmed)
        self.assertEqual(reported, 99)
        self.assertEqual(latest, 100)
        self.assertEqual(hass.services.calls, [])

    async def test_configured_allowance_can_exceed_entity_step(self):
        hass = Hass({"number.target": State(98, {"step": 1})})
        confirmed, *_ = await writer._write_and_verify(
            hass, "number.target", 100, 2
        )
        self.assertTrue(confirmed)
        self.assertEqual(hass.services.calls, [])

    async def test_write_uses_explicit_entity_target(self):
        hass = Hass({"number.target": State(50, {"step": 1})})
        confirmed, reported, _ = await writer._write_and_verify(
            hass, "number.target", 100, 0
        )
        self.assertTrue(confirmed)
        self.assertEqual(reported, 100)
        self.assertEqual(hass.services.calls[0][4], {"entity_id": "number.target"})

    async def test_failed_readback_is_rejected_after_retry(self):
        hass = Hass({"number.target": State(50, {"step": 1})}, update=False)
        original_sleep = asyncio.sleep

        async def no_sleep(_delay):
            return None

        asyncio.sleep = no_sleep
        try:
            confirmed, reported, _ = await writer._write_and_verify(
                hass, "number.target", 100, 0
            )
        finally:
            asyncio.sleep = original_sleep
        self.assertFalse(confirmed)
        self.assertEqual(reported, 50)
        self.assertEqual(len(hass.services.calls), 2)

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

