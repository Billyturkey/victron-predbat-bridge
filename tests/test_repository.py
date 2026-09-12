"""Repository metadata tests for Home Assistant and HACS discovery."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class RepositoryTests(unittest.TestCase):
    def test_manifest_enables_add_integration_flow(self):
        manifest = json.loads(
            (ROOT / "custom_components/victron_predbat_bridge/manifest.json").read_text()
        )
        self.assertEqual(manifest["domain"], "victron_predbat_bridge")
        self.assertEqual(manifest["name"], "Victron Predbat Bridge")
        self.assertTrue(manifest["config_flow"])
        self.assertTrue(manifest["version"])

    def test_hacs_metadata_identifies_an_integration(self):
        hacs = json.loads((ROOT / "hacs.json").read_text())
        self.assertEqual(hacs["name"], "Victron Predbat Bridge")
        self.assertTrue(hacs["homeassistant"])

    def test_setup_guide_and_dashboard_are_shipped(self):
        self.assertTrue((ROOT / "SETUP.md").is_file())
        self.assertTrue((ROOT / "examples/dashboard-billyturkey.yaml").is_file())
        self.assertTrue((ROOT / "examples/predbat-apps.yaml").is_file())


if __name__ == "__main__":
    unittest.main()
