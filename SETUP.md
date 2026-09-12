# Setup guide

This guide installs Victron Predbat Bridge as a Home Assistant integration and
connects it to Predbat. Complete the setup with Victron writes locked, then
observe the planned commands before allowing control of the Victron settings.

## Before you begin

You need:

- Home Assistant 2026.1 or newer;
- a working Victron GX or Victron MQTT integration;
- Predbat running in AppDaemon;
- whole-system battery, grid, load and PV sensors;
- the four writable Victron number entities listed below.

The bridge is not a hardware safety system. Set every electrical limit for the
actual inverter, batteries, cables, fuses, grid connection and supply.

## Install with HACS

Until the repository is accepted into the HACS default catalogue, add it as a
custom repository:

1. Open **HACS** in Home Assistant.
2. Open the three-dot menu and select **Custom repositories**.
3. Enter `https://github.com/Billyturkey/victron-predbat-bridge`.
4. Select **Integration** as the category and add it.
5. Open **Victron Predbat Bridge** in HACS and select **Download**.
6. Restart Home Assistant.
7. Open **Settings > Devices & services > Add integration**.
8. Search for **Victron Predbat Bridge**.

## Install manually

1. Download the latest release ZIP and extract it.
2. Copy the `victron_predbat_bridge` directory into
   `/config/custom_components/`.
3. Confirm that this file exists:
   `/config/custom_components/victron_predbat_bridge/manifest.json`.
4. Restart Home Assistant.
5. Open **Settings > Devices & services > Add integration** and search for
   **Victron Predbat Bridge**.

If it does not appear, clear the browser cache, confirm the directory name is
exactly `victron_predbat_bridge`, restart Home Assistant again, and inspect the
Home Assistant log for `victron_predbat_bridge`.

## Select entities

The setup screen attempts to prefill entities from the official Victron GX
integration or Victron MQTT. Review every selection.

| Selection | Required value |
|---|---|
| Battery SOC | Whole battery-system percentage sensor |
| Battery power | Whole battery-system power sensor |
| Battery voltage | Whole battery-system voltage sensor |
| Grid power | Whole Victron grid power sensor |
| Load power | Whole Victron load power sensor |
| PV power | DC PV power sensor |
| External EV power | Optional load outside the Victron meter |
| AC power setpoint | GX ESS AC power setpoint number |
| Maximum charge current | GX ESS maximum charge-current number |
| Maximum inverter power | GX ESS maximum inverter-power number |
| Minimum SOC | GX ESS minimum-SOC number |

For three-phase installations, use aggregate whole-system grid and load values.

## Configure limits and safety checks

Open the integration and select **Configure**. Set the installation limits,
power sign conventions and request timeout. Then select all native safety
entities:

- parallel system connected;
- ESS mode;
- Hub4 mode;
- Dynamic ESS mode;
- inverter/charger mode;
- native charge schedules 0 through 4.

Leave all four verification allowances at zero initially. The bridge
automatically uses each number entity's advertised step. Add an allowance only
if that integration reports a coarser value than its advertised step.

Leave the risk acknowledgement off during initial checks.

## Connect Predbat

Predbat must call `victron_predbat_bridge.request` whenever its requested mode
or target is refreshed. A charge request looks like this:

```yaml
service: victron_predbat_bridge.request
data:
  direction: charge
  request: charge
  target_soc: 80
  power: 3000
```

An export request uses `direction: export`, `request: export`, the export stop
SOC in `target_soc`, and the requested export power. Send `request: "off"` for
the corresponding direction when the request ends.

The service call should be repeated before the configured request timeout. If
requests stop, the freshness gate becomes invalid and active control restores
the captured settings.

## Shadow test

1. Turn **Control** on.
2. Keep **Allow Victron writes** off.
3. Send demand, charge, preserve and export requests from Predbat.
4. Confirm the planned grid setpoint, charge current, inverter limit and minimum
   SOC are suitable in every mode.
5. Confirm **Safety gate** is valid and all diagnostic checks are valid.

The shadow values are the bridge's current plan. They remain useful after live
writes are enabled because they show the intended value beside the value
reported by Victron.

## First guarded-write test

1. Stop every previous automation that writes to the same four Victron numbers.
2. Confirm the GX AC power setpoint has returned close to its normal idle value.
3. In **Configure**, enable the risk acknowledgement and save.
4. Wait for a fresh Predbat request and confirm **Safety gate** is valid.
5. Start during an ordinary demand period and turn **Allow Victron writes** on.
6. Confirm **Settings ownership** becomes `owned` and **Write status** reports
   that all settings were confirmed.
7. Turn **Allow Victron writes** off.
8. Confirm ownership becomes `released`, writes become locked, and the four
   original Victron settings are restored.

Test charge and export only after this restoration test succeeds. Also test a
Home Assistant restart, a stale Predbat request and an unavailable safety
entity. Each must leave writes locked or restore the captured settings.

## Add the dashboard

Create a new Home Assistant dashboard, open its raw configuration editor and
paste the contents of `examples/dashboard-billyturkey.yaml`. That example uses
the entity IDs from the original two-MultiPlus installation. Replace any entity
ID that differs on another installation.

