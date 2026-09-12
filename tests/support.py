"""Small Home Assistant stand-ins for isolated bridge unit tests."""

from __future__ import annotations

import importlib.util
import sys
import types
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).parents[1]
PACKAGE = "custom_components.victron_predbat_bridge"


class State:
    def __init__(self, state, attributes=None):
        self.state = str(state)
        self.attributes = attributes or {}


class States:
    def __init__(self, values=None):
        self.values = values or {}

    def get(self, entity_id):
        return self.values.get(entity_id)


class Services:
    def __init__(self, states, update=True):
        self.states = states
        self.update = update
        self.calls = []

    async def async_call(self, domain, service, data, *, blocking, target):
        self.calls.append((domain, service, data, blocking, target))
        if self.update:
            self.states.values[target["entity_id"]].state = str(data["value"])


class Hass:
    def __init__(self, values=None, update=True):
        self.states = States(values)
        self.services = Services(self.states, update)
        self.data = {}


def _module(name, **attributes):
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


def load_bridge_modules():
    """Load controller and writer without requiring a Home Assistant install."""
    if f"{PACKAGE}.controller" in sys.modules:
        return (
            sys.modules[f"{PACKAGE}.const"],
            sys.modules[f"{PACKAGE}.controller"],
            sys.modules[f"{PACKAGE}.writer"],
        )

    class Platform:
        SENSOR = "sensor"
        SWITCH = "switch"

    class HomeAssistantError(Exception):
        pass

    ha = _module("homeassistant")
    ha.__path__ = []
    _module("homeassistant.const", Platform=Platform)
    _module("homeassistant.core", HomeAssistant=object)
    _module("homeassistant.config_entries", ConfigEntry=object)
    _module("homeassistant.exceptions", HomeAssistantError=HomeAssistantError)
    helpers = _module("homeassistant.helpers")
    helpers.__path__ = []
    _module("homeassistant.helpers.dispatcher", async_dispatcher_send=lambda *args: None)
    util = _module("homeassistant.util")
    util.__path__ = []
    dt_module = _module(
        "homeassistant.util.dt", utcnow=lambda: datetime.now(timezone.utc)
    )
    util.dt = dt_module

    custom_components = types.ModuleType("custom_components")
    custom_components.__path__ = [str(ROOT / "custom_components")]
    sys.modules["custom_components"] = custom_components
    package = types.ModuleType(PACKAGE)
    package.__path__ = [str(ROOT / "custom_components" / "victron_predbat_bridge")]
    sys.modules[PACKAGE] = package

    loaded = []
    for name in ("const", "controller", "writer"):
        full_name = f"{PACKAGE}.{name}"
        path = ROOT / "custom_components" / "victron_predbat_bridge" / f"{name}.py"
        spec = importlib.util.spec_from_file_location(full_name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[full_name] = module
        spec.loader.exec_module(module)
        loaded.append(module)
    return tuple(loaded)

