# Xenia Home

> [!IMPORTANT]
> This project is an unofficial Home Assistant integration for controlling and monitoring espresso machines produced by Xenia Espresso GmbH.
> It is **not affiliated with, endorsed by, or supported by Xenia Espresso GmbH** in any way.
> All product and company names, trademarks, and registered trademarks are the property of their respective owners.
> Use of names or trademarks in this project is solely for identification purposes to indicate device compatibility.
> This software is provided "as is", without any warranty. Use at your own risk.

The **Xenia Espresso Machine** integration brings the commercial-grade
espresso machines made by [Xenia Espresso GmbH](https://www.xenia-espresso.de/)
into Home Assistant. It talks to your machine over the local network (no
cloud account is required) and exposes the machine's state, settings, and
on-device scripts as Home Assistant entities.

With it installed you can monitor temperatures, pressures, energy usage, and
extraction counters; toggle power, ECO mode, and the steam boiler from a
dashboard or automation; adjust brew-group and brew-boiler setpoints; bind
the machine's physical switch positions to scripts; track every shot with
its temperature, pressure, flow rate, and final weight; and, if your
machine runs a weight-target script, change that target directly from Home
Assistant.

## Supported devices

- Xenia DBL with API v2
- Other Xenia models may work but are untested

## Installation

### Prerequisites

- A running Home Assistant installation.
- A Xenia espresso machine with API v2 firmware (for example Xenia DBL), powered on and reachable from your Home Assistant host on the local network.
- The machine's hostname or IP address (visible in the machine's built-in web UI or in your router's DHCP client list).
- For Home Assistant 2026.10: [HACS](https://hacs.xyz/) installed and configured. From 2026.11 on, HACS is built into Home Assistant as the Marketplace.

### Marketplace (Home Assistant 2026.11 and later, recommended)

1. Go to **Settings → Marketplace** and select **Add from link** in the upper-right corner.
2. Enter `https://github.com/Knoedelauflauf/xenia-home` and select **Add**. Adding a custom repository needs a GitHub connection; the Marketplace asks you to connect if you have not yet.
3. Open **Xenia Espresso Machine** and select **Install**.
4. The setup opens right after the install. Enter the hostname or IP address of the machine.

Updates appear under **Settings → Updates** and need a restart, which a repair under **Settings → System → Repairs** offers to do for you.

### HACS (Home Assistant 2026.10)

1. In Home Assistant, open HACS.
2. Open the three-dot menu in the top right and choose **Custom repositories**.
3. Add `https://github.com/Knoedelauflauf/xenia-home` with category **Integration**, then click **Add**.
4. Search HACS for **Xenia Espresso Machine** and install it.
5. Restart Home Assistant.
6. Go to **Settings → Devices & Services → Add Integration** and choose **Xenia Espresso Machine**.

### Manual

1. Download the latest release archive from the [Releases page](https://github.com/Knoedelauflauf/xenia-home/releases).
2. Extract it and copy the `custom_components/xenia_home/` folder into your Home Assistant `config/custom_components/` directory.
3. Restart Home Assistant.
4. Go to **Settings → Devices & Services → Add Integration** and choose **Xenia Espresso Machine**.

## Configuration

When you add the integration you are asked for the **Host** of your machine.
Enter the hostname or IP address of the Xenia controller on your local
network, for example `xenia.local` or `192.168.1.42`. Do not include a
URL scheme (`http://`) or a port number; enter only the bare hostname or
IPv4 address. You can find the value in the machine's built-in web UI or in
your router's DHCP client list.

The integration verifies that it can reach the machine before the entry is
created, so an invalid host fails fast during setup. The host can be
changed later from the integration's **…** menu under **Reconfigure**.
The machine is recognized by its MAC address: adding it again under a new
host updates the host of the existing entry, and **Reconfigure** only
accepts a host that answers as the same machine. When a machine set up by
IP address gets a new one, Home Assistant picks it up from the machine's
DHCP request; a hostname is kept.

### Options

Open **Configure** on the integration entry to change the following
settings.

**Enable weight management.** When enabled, you can pick a script on the
machine whose brew weight target should be exposed as a Home Assistant
number entity. This lets you change the final brew weight from a dashboard
or automation without using the machine's own web UI. After enabling, you
are prompted to either select an existing script that already has a weight
target, or create a new one (the new script is named "HA Espresso" on the
machine).

**Weight target settings.** Set the minimum, maximum, and step size (in
grams) of the weight target number entity. Defaults: minimum 25 g, maximum
50 g, step 0.5 g. The maximum must be above the minimum and the step above
0. Pick a range that matches the shots you actually pull.

## Entities

All entities belong to one device per machine. Entities marked *disabled*
start disabled; enable them on the entity's settings page.

**Sensors**

| Entity | Description |
|--------|-------------|
| Brewgroup temperature, Brewboiler temperature | Current temperatures in °C. |
| Pump pressure, Steamboiler pressure | Current pressures in bar. |
| Total energy | Energy counter of the machine in kWh, for the energy dashboard. |
| Scale flow rate | Flow from the scale in g/s. Only created on firmware that reports it. |
| Status | Off, On, Eco, Brewing, Draining or Unknown. |
| Shot start time | Start of the running shot, `unknown` otherwise (see **Shot timer**). |
| Extractions, Operating hours | Counters of the machine (diagnostic). |
| Electric current | Raw current reading of the controller in A (diagnostic, *disabled*). |

**Binary sensor:** *Water tank empty* turns on when the tank needs water.

**Numbers:** *Brewgroup set temperature* and *Brewboiler set temperature*
change the setpoints. *Script weight target* appears when weight management
is enabled (see **Weight management**).

**Switches:** *Power* turns the machine on, following the power on
behavior, or off. *ECO mode* puts the running machine into eco mode or back.
*Steam boiler power* switches the steam boiler while the machine is on.

**Selects**

| Entity | Description |
|--------|-------------|
| Power on behavior | Whether the steam boiler turns on with the machine. Kept by Home Assistant, not by the machine. |
| Script | The script the *Execute script* button runs. |
| Left switch left short, ... Right switch right long | The script each of the six switch positions runs (*disabled*). |

**Buttons:** *Execute script* runs the script picked in *Script*; *Stop
script* stops the running script; *Tare scale* tares the Bluetooth scale
connected to the machine (see **Scale tare**).

**Event:** *Shot tracker* fires `shot_completed` with the curves of every
shot of ten seconds or more (see **Shot history API**).

## Shot timer

The integration does not count seconds itself. The shot start time sensor
holds the start of the running shot and is `unknown` otherwise; the shot
tracker event carries the final `duration_seconds` once the shot is done.
The start is the moment Home Assistant first saw the shot, so a shot that
is already running when the integration loads is timed from the load.

An entities card with `time_format: total` counts up on its own, no
helper needed:

```yaml
type: entities
entities:
  - entity: sensor.xenia_espresso_machine_shot_start_time
    time_format: total
```

To show the running timer only while brewing and the duration of the last
shot otherwise, stack two conditional cards:

```yaml
type: vertical-stack
cards:
  - type: conditional
    conditions:
      - condition: state
        entity: sensor.xenia_espresso_machine_status
        state: brewing
    card:
      type: entities
      entities:
        - entity: sensor.xenia_espresso_machine_shot_start_time
          name: Shot
          time_format: total
  - type: conditional
    conditions:
      - condition: state
        entity: sensor.xenia_espresso_machine_status
        state_not: brewing
    card:
      type: entities
      entities:
        - type: attribute
          entity: event.xenia_espresso_machine_shot_tracker
          attribute: duration_seconds
          name: Last shot
          suffix: s
```

For a gauge or tile, or to keep the value visible after the shot, use the
shot timer blueprint: it writes the seconds into a number helper.

1. Create a number helper under Settings > Devices & services > Helpers
   (minimum 0, maximum 100, step 1).
2. Import the blueprint:
   [![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FKnoedelauflauf%2Fxenia-home%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fxenia_home%2Fshot_timer.yaml)
3. Create an automation from it and pick the three sensors and the helper.

Optional but recommended: the helper changes every second while a shot
runs, and every change is a row in the recorder database. To keep it out,
add the helper to the `recorder` section of your `configuration.yaml`
(create the section if it does not exist) and restart Home Assistant:

```yaml
recorder:
  exclude:
    entities:
      - input_number.xenia_shot_timer
```

## Actions

### Action: `xenia_home.execute_script`

Execute a script that is stored on the Xenia machine. Provide either the
numeric ID of the script or its name; if both are supplied, `script_id`
wins and `script_name` is ignored.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `config_entry_id` | string | Only with several machines | The config entry of the machine to use. With a single machine it can be left out. |
| `script_id` | integer | One of `script_id` / `script_name` is required | Numeric ID (≥ 1) of the script as stored on the machine. Takes precedence over `script_name` when both are supplied. |
| `script_name` | string | One of `script_id` / `script_name` is required | Name of the script as the script select shows it. Scripts that share a name are shown with their ID added, for example `Espresso (12)`. Ignored when `script_id` is also supplied. |

Example automation step:

```yaml
action: xenia_home.execute_script
data:
  script_name: "Espresso 18g"
```

To stop the script currently running, press the "Stop script" button
entity, from a dashboard or via `button.press` in an automation.

## Weight management

When weight management is enabled (see **Options** above), the integration
exposes the brew weight target of a chosen on-device script as a Home
Assistant number entity. Adjusting that entity rewrites the weight target
on the machine, so the next shot pulled with that script stops at the new
weight. You can also bind the number entity into automations, for
example, to step the target down by 0.5 g across a tasting flight, or to
expose a slider on a dashboard.

## Scale tare

With firmware 4.255 the machine tares its Bluetooth scale only before a
script started over the API, as the *Execute script* button and the
`xenia_home.execute_script` action do, and when it returns to ready after a
shot. A shot started with the switches on the machine is not tared at its
start, so with a cup already on the scale a weight target counts as reached
right away.

To tare at every shot start, press the *Tare scale* button from an
automation. Home Assistant sees the start within about a second:

```yaml
triggers:
  - trigger: state
    entity_id: sensor.xenia_espresso_machine_status
    to: brewing
actions:
  - action: button.press
    target:
      entity_id: button.xenia_espresso_machine_tare_scale
```

## Shot history API

The integration stores every completed shot itself (indefinitely, in
`.storage/xenia_home/`); history does not depend on the recorder and survives recorder
purges. Other apps can query it over the Home Assistant WebSocket API with any
authenticated connection; a long-lived access token is enough. Reading needs
no admin rights, deleting does.

Timestamps are millisecond-precision ISO 8601 strings, directly parseable
with JavaScript's `new Date(...)`. A shot's `shot_id` is its `start_time`.
Timestamp inputs (`after`/`before`) accept any ISO 8601 string; naive
timestamps are interpreted in the Home Assistant server's local time zone.

**`xenia_home/shots/list`**: summaries, newest first, one entry per shot.
Optional: `entry_id` (only needed with several Xenia entries), `after` /
`before` (ISO timestamps, exclusive bounds on `start_time`), `limit`.
Result: `{"shots": [{"shot_id", "start_time", "brew_end_time",
"duration_seconds", "final_weight_g"}, ...]}`. Paging, if ever needed, is
keyset-style: pass the oldest received `start_time` as `before`.

**`xenia_home/shots/get`**: full curves. Required: `shot_ids` (list).
Result: `{"shots": [...]}` in request order; each entry is the complete
`shot_completed` event payload plus `shot_id`, unknown ids are omitted.

**`xenia_home/shots/delete`**: remove one shot. Required: `shot_id`.
Admin users only, others get `unauthorized`. Errors with code `not_found` for
unknown ids.

All commands error with `not_found` (no or unknown entry) and
`multiple_entries` (several entries loaded but no `entry_id` given);
`shots/list` errors with `invalid_format` for unparseable `after`/`before`.

Live data is unchanged: the `shot_completed` event still carries the full
payload. Note for recorder-based consumers: from this version on, recorder
rows of the event entity no longer contain the curve arrays, so switch to
the commands above for history.

## Frontend card

For visualizing shot tracking data, check out [xenia-home-card](https://github.com/Knoedelauflauf/xenia-home-card).

## Data updates

The integration polls the machine over the local network. It reads the live
values once per second while the machine is on or brewing and every five
seconds while it is in eco mode or off; the one second interval sets the
time resolution of shot tracking. The set temperatures and the water tank
level are read every ten seconds. Every command is followed by a poll one
second later, since the machine reports its effect only then. Firmware
versions, scripts, switch assignments and the managed script are read once
per hour, and again after a minute when that read fails. The machine answers
one request at a time, so reads, commands and the options dialog send their
requests one after another.

To poll at a different rate, disable **Polling for updates** in the entry's
system options and call `homeassistant.update_entity` from an automation.
An update of a live value reads only the live values; the set temperatures
and the water tank level are read when the automation updates one of them
or after a temperature is set. The script and switch names are then
refreshed only after a command that changes them, or when the entry is
reloaded.

## Known limitations

- Only the Xenia DBL with API v2 is tested. Other Xenia models may work.
- The electric current reading does not drop to zero while the machine is
  off (about 1.3 A on a DBL), and the energy counter does not move then.
- A shot is timed from the moment Home Assistant first sees it brewing, at
  most one second late. A shot already running when the integration loads
  is timed from the load.
- The machine stops the pump after 60 seconds unless it is set to extreme
  values. If the machine does not answer for a while during a shot, the
  shot ends at its last answer that still showed brewing. Brewing seen again
  more than 60 seconds after the shot start is then recorded as a new shot.
- The power on behavior is kept by Home Assistant. Turning the machine on
  at the machine itself does not follow it.
- Shots shorter than ten seconds, like flushes, are not tracked.

## Troubleshooting

### Setup fails with "Failed to connect"

The host is wrong or the machine is not reachable. Open the machine's web
UI in a browser on the same network with the same host. If that fails too,
check the IP address in your router, and give the machine a fixed address
so it keeps it.

### All entities are unavailable

Home Assistant cannot reach the machine anymore, usually because it got a
new IP address or is unplugged. If the address changed and Home Assistant
did not pick it up from DHCP, use **Reconfigure** on the integration entry
and enter the new one; entities, history and automations stay.

### The entry fails with "already set up as"

The same machine was added twice in an earlier release, under two
addresses. Delete the entry that shows the message; the entry it names
keeps working.

### The script weight target is unavailable

The managed script was deleted on the machine, or could not be read. A
deleted script raises a repair issue under **Settings → System → Repairs**;
open **Configure** on the integration entry and pick another script, or
turn weight management off. A script that could not be read is read again
every minute, and the failure is logged once.

## Removing the integration

- **Marketplace:** open **Xenia Espresso Machine** under **Settings → Marketplace**, select **Uninstall** in the three-dot menu and choose **Delete and uninstall**. This removes the setup with its devices and entities and then the files. If Home Assistant asks for a restart under **Settings → System → Repairs**, restart it.
- **HACS or manual install:** delete the integration under **Settings → Devices & Services** (three-dot menu on the Xenia Espresso Machine card, **Delete**). Then uninstall it in HACS, or for a manual install delete the `custom_components/xenia_home/` folder from your Home Assistant `config/` directory, and restart Home Assistant.

The Xenia espresso machine itself stores no Home Assistant–specific data,
so no cleanup on the machine is necessary. If you previously enabled weight
management and let the integration create a new on-device script for you,
you may optionally delete that script from the machine's web UI. Shot
history is stored by the integration and is deleted together with it; other
recorded entity history is kept by the Home Assistant recorder until it
ages out of the recorder's retention window or you purge it manually.
