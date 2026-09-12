# Victron Predbat Bridge

A Home Assistant custom integration that will connect Predbat requests to a
Victron ESS through the official Victron GX integration.

For installation, entity selection, Predbat service calls and first-write
testing, see the **[setup guide](SETUP.md)**.

> [!CAUTION]
> **USE ENTIRELY AT YOUR OWN RISK.**
>
> This is an unofficial community project. It can eventually send commands to
> battery and inverter equipment. Incorrect entities, sign conventions, limits,
> wiring, fuses, battery settings, or software behaviour could cause equipment
> damage, loss of power, excessive import or export, battery stress, fire, injury,
> or financial loss. It is not endorsed or supported by Victron Energy,
> Home Assistant, Predbat, or the battery manufacturer.
>
> You are responsible for checking the design and installation with a suitably
> qualified person, following every equipment manufacturer's instructions, and
> setting limits suitable for your own inverter, batteries, cables, fuses, grid
> connection, and electricity supply. Keep the bridge control disabled until all
> selected entities, power signs, safety limits, fail-safe behaviour, and manual
> recovery have been verified. Never rely on this software as a safety device.
> The authors and contributors accept no liability for its use.

## Current experimental build

Version 0.6.0 adds an experimental guarded-write mode. It remains locked unless
the risk acknowledgement is enabled under **Configure**, the bridge **Control**
switch is on, every safety check passes, and **Allow Victron writes** is manually
turned on. The write switch preserves the user's armed choice across a restart,
but no writes resume until a fresh Predbat request arrives and every safety
check passes. A deliberate switch-off remains off.

Before the first write, the bridge captures the selected grid setpoint, charge
current limit, inverter limit and minimum SOC. It refuses to capture a grid
setpoint outside ±200 W, which helps prevent taking ownership while another
controller is active. Every command is read back after writing. A failed write,
stale Predbat request, failed safety check, disabled switch, reload or clean
restart restores the captured settings. Recovery data is stored so an unclean
restart can restore it when the integration next starts. After recovery, an
armed bridge waits for fresh safe instructions before taking control again.
If Victron entities are not ready during startup, pending recovery is retried
when their states return and on the periodic safety check.

The device page keeps controller state and shadow commands together under
Sensors. Detailed source, request and native ESS checks appear under the
Diagnostics section so the normal operating view remains easier to scan.

Write verification uses each selected number entity's advertised step rather
than installation-specific hard-coded tolerances. It checks feedback against
both the command sent and the latest shadow calculation. If neither matches, it
retries once with the latest command before restoring and disarming. Optional
additional allowances can be configured for integrations whose reported values
need them; zero means use the entity resolution only. Failure messages include
the original request, latest target and reported value.

Number services use Home Assistant's explicit entity target field. The write
gate remains closed after a failure, including for state-change callbacks that
were already queued.
Rapid source telemetry updates recalculate the displayed shadow plan without
writing every small change. Commands are applied on a fresh Predbat request and
the 30-second control cycle, matching the proven YAML controller's cadence.
Safety failures still trigger immediate restoration.

The integration also lets you:

- install the integration through the Home Assistant UI;
- automatically discover and prefill entities owned by the official Victron GX
  integration or Tomer W's Victron MQTT integration, while still requiring the
  user to confirm them;
- enable or disable request processing with a switch that survives restarts;
- send a Predbat request and inspect the grid, current, inverter and minimum-SOC
  commands that would be applied.
- edit installation-specific electrical limits through the integration's
  **Configure** button without reinstalling it.
- verify Predbat request freshness, Victron control availability, native ESS
  modes and all five native charge schedules before future writes are allowed.

Keep the write acknowledgement and **Allow Victron writes** off while comparing
shadow results. Enabling guarded writes transfers control of the four selected
Victron number entities to this integration.

## System limits

Open **Settings > Devices & services > Victron Predbat Bridge > Configure** to
set the limits for the installation. The included defaults match the original
two-MultiPlus test system and must be reviewed by every other user.

Shadow commands are limited by both these settings and the minimum/maximum
range advertised by each selected Home Assistant number entity. The configured
hardware limit must reflect the inverter, battery/BMS, cables, fuses, supply and
grid permission; an entity's maximum value is not evidence that the installation
can safely use it.

For a three-phase installation, select `3` and provide aggregate whole-system
grid and load sensors. A single phase sensor is not a valid whole-site input.

The **Safe for future writes** sensor means the configured entities, native ESS
state and request freshness passed the software checks. It cannot validate the
physical installation or prove that the configured limits are safe.

## Install locally for development

1. Back up Home Assistant.
2. Open the Home Assistant configuration folder using Studio Code Server,
   Samba, or File editor.
3. Create `/config/custom_components` if it does not exist.
4. Copy the entire `victron_predbat_bridge` folder from this repository's
   `custom_components` folder to:

   `/config/custom_components/victron_predbat_bridge`

5. Restart Home Assistant.
6. Go to **Settings > Devices & services > Add integration**.
7. Search for **Victron Predbat Bridge**. Matching Victron GX entities are
   prefilled automatically. Check them and add the optional external EV sensor.

HACS is not required during local development. Once this repository is on
GitHub, it can be installed as a HACS custom repository.

## Test dashboard

`examples/dashboard-billyturkey.yaml` is a complete Home Assistant dashboard
for the two-MultiPlus test installation. It uses built-in Home Assistant cards
and has separate Bridge, Trends and Alarms views. The bridge's shadow entities
are labelled **Planned commands** on the dashboard because they represent the
latest calculated commands whether guarded writes are locked or active.

To add it, create a new dashboard, open its raw configuration editor and paste
the file contents. Entity IDs are based on the test installation and can be
changed in the editor if Home Assistant assigned a different bridge entity ID.

## Entity selections for Billyturkey's test system

| Field | Entity |
|---|---|
| Battery SOC | `sensor.garage_gx_device_dc_battery_charge` |
| Battery power | `sensor.garage_gx_device_dc_battery_power` |
| Battery voltage | `sensor.garage_gx_device_dc_battery_voltage` |
| Victron grid power | `sensor.garage_gx_device_grid_power_l1` |
| Victron load power | `sensor.garage_gx_device_consumption_power_l1` |
| DC PV power | `sensor.garage_gx_device_pv_power` |
| External EV power | `sensor.outside_hypervolt_ev_charger_hypervolt_ev_power` |
| GX AC power setpoint | `number.garage_gx_device_ac_power_setpoint` |
| Maximum charge current | `number.garage_gx_device_ess_max_charge_current` |
| Maximum inverter power | `number.garage_gx_device_ess_max_inverter_power_limit` |
| Minimum SOC | `number.garage_gx_device_ess_min_soc_limit` |

Other users choose their own matching entities on this screen; no entity IDs
are hard-coded in the integration.

## First guarded-write test

After adding the integration:

1. Find the **Victron Predbat Bridge** device.
2. Leave **Allow Victron writes** off and turn **Control** on.
3. Go to **Developer tools > Actions**.
4. Run `victron_predbat_bridge.request` with:

```yaml
direction: charge
request: charge
target_soc: 80
power: 3000
```

The shadow command sensors should update and no Victron number should change.

When all shadow tests pass, stop the previous controller and confirm it has
restored the normal grid setpoint. Open **Configure**, read the warning, enable
the risk acknowledgement, and save. Wait for a fresh Predbat request and confirm
all safety sensors are valid. Turn **Allow Victron writes** on first during a
normal demand period. Check **Write status** reports that all four settings were
confirmed. Turn it off and verify **Settings ownership** is `released` and the
original four settings have been restored before testing charge or export.

Restart Home Assistant and confirm that the Control switch keeps its previous
state. Then send an `off` request:

```yaml
direction: charge
request: "off"
```

## Development stages

1. Receiver-only setup and restart test.
2. Shadow controller that calculates and displays intended Victron commands.
3. Guarded write mode with acknowledgement, freshness checks, verified writes
   and restoration (this release).
4. Predbat callback examples, documentation, automated validation, and a HACS
   release.

## HACS repository structure

The repository follows the required layout:

```text
hacs.json
custom_components/
  victron_predbat_bridge/
    __init__.py
    config_flow.py
    manifest.json
    sensor.py
    services.yaml
    strings.json
    switch.py
    translations/en.json
```
