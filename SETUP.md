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

Leave the risk acknowledgement off during initial checks.

The same **Configure** form can be used later to change any source sensor,
Victron number control, optional EV sensor, limit or safety entity. Saving the
form safely disarms writes, restores any settings currently owned by the bridge,
then reloads the integration with the new selections. **Allow Victron writes**
must be deliberately enabled again after any configuration change.

## Connect Predbat

Predbat must call `victron_predbat_bridge.request` whenever its requested mode
or target is refreshed. Edit the `apps.yaml` file used by the Predbat AppDaemon
add-on. Find the existing `pred_bat:` section and add or replace these five
service blocks inside it:

```yaml
pred_bat:
  # Keep your existing Predbat settings above and below these blocks.
  charge_start_service:
  - service: victron_predbat_bridge.request
    always: true
    direction: charge
    request: charge
    target_soc: '{target_soc}'
    power: '{power}'

  charge_stop_service:
  - service: victron_predbat_bridge.request
    always: true
    direction: charge
    request: 'off'

  charge_freeze_service:
  - service: victron_predbat_bridge.request
    always: true
    direction: charge
    request: preserve
    target_soc: '{target_soc}'
    power: '{power}'

  discharge_start_service:
  - service: victron_predbat_bridge.request
    always: true
    direction: export
    request: export
    target_soc: '{target_soc}'
    power: '{power}'

  discharge_stop_service:
  - service: victron_predbat_bridge.request
    always: true
    direction: export
    request: 'off'
```

The complete copy-and-paste example is in
[`examples/predbat-apps.yaml`](examples/predbat-apps.yaml). The `pred_bat:` line
already exists in a normal Predbat configuration. Merge the five service keys
under that existing line; do not create a second `pred_bat:` app.

If any of those keys already call an older script or controller, remove that
old service entry. Each event should call the bridge once. Other unrelated
service entries may remain if you deliberately need them.

`charge_start_service` sends the requested charge target and power.
`charge_freeze_service` asks the bridge to preserve the battery. The two stop
services clear their respective requests. `discharge_start_service` maps
Predbat discharge/export control to the bridge's export request.

Save `apps.yaml`, then restart the Predbat AppDaemon add-on or reload its apps.
Check the Predbat log for YAML or service errors. Within the request timeout,
the bridge's **Last Predbat request** should update and **Predbat request
freshness** should become `valid`.

The service call should be repeated before the configured request timeout. If
requests stop, the freshness gate becomes invalid and active control restores
the captured settings.

To test the Home Assistant service independently of Predbat, open **Developer
tools > Actions** and call `victron_predbat_bridge.request` with:

```yaml
direction: charge
request: charge
target_soc: 80
power: 3000
```

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
   `Guarded writes active — commands sent`.
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
