"""Tests for controller plans and safety gates."""

from __future__ import annotations

import types
import unittest
from datetime import datetime, timezone

from support import Hass, State, load_bridge_modules


const, controller, _writer = load_bridge_modules()


def setup_case():
    config = {
        const.CONF_BATTERY_SOC: "sensor.soc",
        const.CONF_BATTERY_POWER: "sensor.battery_power",
        const.CONF_BATTERY_VOLTAGE: "sensor.voltage",
        const.CONF_GRID_POWER: "sensor.grid",
        const.CONF_LOAD_POWER: "sensor.load",
        const.CONF_PV_POWER: "sensor.pv",
        const.CONF_EV_POWER: "sensor.ev",
        const.CONF_AC_SETPOINT: "number.grid_target",
        const.CONF_MAX_CHARGE_CURRENT: "number.current",
        const.CONF_MAX_INVERTER_POWER: "number.inverter",
        const.CONF_MIN_SOC: "number.min_soc",
    }
    options = {
        const.OPT_CONNECTED_ENTITY: "binary_sensor.connected",
        const.OPT_ESS_MODE_ENTITY: "select.ess",
        const.OPT_HUB4_MODE_ENTITY: "select.hub4",
        const.OPT_DESS_MODE_ENTITY: "select.dess",
        const.OPT_INVERTER_MODE_ENTITY: "select.inverter_mode",
        const.OPT_SCHEDULE_0_ENTITY: "select.schedule_0",
        const.OPT_SCHEDULE_1_ENTITY: "select.schedule_1",
        const.OPT_SCHEDULE_2_ENTITY: "select.schedule_2",
        const.OPT_SCHEDULE_3_ENTITY: "select.schedule_3",
        const.OPT_SCHEDULE_4_ENTITY: "select.schedule_4",
    }
    values = {
        "sensor.soc": State(50), "sensor.battery_power": State(0),
        "sensor.voltage": State(50), "sensor.grid": State(0),
        "sensor.load": State(500), "sensor.pv": State(0), "sensor.ev": State(0),
        "number.grid_target": State(50, {"min": -10000, "max": 10000}),
        "number.current": State(140, {"min": 0, "max": 140}),
        "number.inverter": State(7399, {"min": 0, "max": 7399}),
        "number.min_soc": State(10, {"min": 0, "max": 100}),
        "binary_sensor.connected": State("on"),
        "select.ess": State("optimized_no_battery_life"),
        "select.hub4": State("phase_compensation_enabled"),
        "select.dess": State("off"), "select.inverter_mode": State("on"),
        **{f"select.schedule_{i}": State("disabled_0") for i in range(5)},
    }
    runtime = types.SimpleNamespace(
        last_request=datetime.now(timezone.utc), charge_request="off",
        export_request="off", charge_target=80, export_target=20,
        charge_power=3000, export_power=7000,
    )
    return Hass(values), config, options, runtime


class ControllerTests(unittest.TestCase):
    def test_demand_plan_is_safe(self):
        hass, config, options, runtime = setup_case()
        result = controller.calculate_shadow(hass, config, options, runtime)
        self.assertEqual(result.intent, "demand")
        self.assertEqual(result.grid_setpoint, 50)
        self.assertTrue(result.safety_ready)

    def test_charge_plan_respects_current_limit(self):
        hass, config, options, runtime = setup_case()
        runtime.charge_request = "charge"
        runtime.charge_power = 20000
        result = controller.calculate_shadow(hass, config, options, runtime)
        self.assertEqual(result.intent, "charge")
        self.assertLessEqual(result.charge_current, 140)
        self.assertLessEqual(result.grid_setpoint, 8000)

    def test_export_plan_and_entity_clamp(self):
        hass, config, options, runtime = setup_case()
        runtime.export_request = "export"
        hass.states.values["number.grid_target"].attributes["min"] = -6000
        result = controller.calculate_shadow(hass, config, options, runtime)
        self.assertEqual(result.intent, "export")
        self.assertEqual(result.grid_setpoint, -6000)
        self.assertEqual(result.inverter_limit, 6999)

    def test_export_is_blocked_while_ev_is_active(self):
        hass, config, options, runtime = setup_case()
        runtime.export_request = "export"
        hass.states.values["sensor.ev"].state = "7000"
        result = controller.calculate_shadow(hass, config, options, runtime)
        self.assertEqual(result.intent, "preserve")
        self.assertIn("EV export blocked", result.note)

    def test_stale_request_closes_safety_gate(self):
        hass, config, options, runtime = setup_case()
        runtime.last_request = None
        result = controller.calculate_shadow(hass, config, options, runtime)
        self.assertEqual(result.intent, "standby")
        self.assertFalse(result.request_fresh)
        self.assertFalse(result.safety_ready)

    def test_native_safety_failure_closes_gate(self):
        hass, config, options, runtime = setup_case()
        hass.states.values["select.dess"].state = "on"
        result = controller.calculate_shadow(hass, config, options, runtime)
        self.assertFalse(result.native_ready)
        self.assertFalse(result.safety_ready)
        self.assertIn("Dynamic ESS", result.safety_note)


if __name__ == "__main__":
    unittest.main()

