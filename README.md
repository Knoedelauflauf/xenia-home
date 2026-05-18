# Xenia Home

> [!IMPORTANT]
> This project is an unofficial Home Assistant integration for controlling and monitoring espresso machines produced by Xenia Espresso GmbH.
> It is **not affiliated with, endorsed by, or supported by Xenia Espresso GmbH** in any way.
> All product and company names, trademarks, and registered trademarks are the property of their respective owners.
> Use of names or trademarks in this project is solely for identification purposes to indicate device compatibility.
> This software is provided "as is", without any warranty. Use at your own risk.

The **Xenia Espresso Machine** integration brings the commercial-grade
espresso machines made by [Xenia Espresso GmbH](https://www.xenia-espresso.de/)
into Home Assistant. It talks to your machine over the local network — no
cloud account is required — and exposes the machine's state, settings, and
on-device scripts as Home Assistant entities.

With it installed you can monitor temperatures, pressures, energy usage, and
extraction counters; toggle power, ECO mode, and the steam boiler from a
dashboard or automation; adjust brew-group and brew-boiler setpoints; bind
the machine's physical switch positions to scripts; track every shot with
its temperature, pressure, flow rate, and final weight; and — if your
machine runs a weight-target script — change that target directly from Home
Assistant.

## Supported devices

- Xenia DBL with API v2
- Other Xenia models may work but are untested

## Installation

### Prerequisites

- A running Home Assistant installation.
- A Xenia espresso machine with API v2 firmware (for example Xenia DBL), powered on and reachable from your Home Assistant host on the local network.
- The machine's hostname or IP address (visible in the machine's built-in web UI or in your router's DHCP client list).
- For the HACS install path: [HACS](https://hacs.xyz/) installed and configured.

### HACS (recommended)

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
network — for example `xenia.local` or `192.168.1.42`. Do not include a
URL scheme (`http://`) or a port number; enter only the bare hostname or
IPv4 address. You can find the value in the machine's built-in web UI or in
your router's DHCP client list.

The integration verifies that it can reach the machine before the entry is
created, so an invalid host fails fast during setup. The host can be
changed later from the integration's **…** menu under **Reconfigure**.

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
50 g, step 0.5 g. Pick a range that matches the shots you actually pull.

**Configure polling intervals (advanced).** Change how often the integration
asks the machine for new sensor data. Each interval is in seconds with a
floor of 0.5 s and a default of 1.0 s, and applies to a different state:

- **Brewing** — polled while a shot is being pulled. This interval also
  determines the time resolution of shot tracking; lower values give finer
  shot detail at the cost of more network traffic.
- **Heating up** — polled while the machine is warming and not yet at the
  ready temperature.
- **Ready** — polled while the machine is at temperature and idle.
- **Idle (eco/off)** — polled when the machine is in ECO mode or powered
  off.
- **Ready temperature threshold (°C)** — the brew-boiler temperature
  difference at or below which the machine is considered ready (and
  switches from the *heating up* interval to the *ready* interval).
  Default: 2.0 °C.

The defaults work well for most users; only touch these if you have a clear
reason to.

## Features

- Power, ECO mode, and steam boiler control
- Brew-group and brew-boiler temperature setpoints
- Live sensors for temperatures, pressures, electric current, total energy, extractions, and operating hours
- Water tank level monitoring
- Trigger any on-device script from Home Assistant (by ID or by name)
- Map each of the six physical switch positions to a script
- Shot tracking with per-shot temperature, pressure, flow rate, and final weight
- Optional weight-target management for a chosen script (see **Options** above)

## Actions

### Action: `xenia_home.execute_script`

Execute a script that is stored on the Xenia machine. Provide either the
numeric ID of the script or its name; if both are supplied, `script_id`
wins and `script_name` is ignored.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `script_id` | integer | One of `script_id` / `script_name` is required | Numeric ID (≥ 1) of the script as stored on the machine. Takes precedence over `script_name` when both are supplied. |
| `script_name` | string | One of `script_id` / `script_name` is required | Name of the script. Ignored when `script_id` is also supplied. |

Example automation step:

```yaml
action: xenia_home.execute_script
data:
  script_name: "Espresso 18g"
```

## Weight management

When weight management is enabled (see **Options** above), the integration
exposes the brew weight target of a chosen on-device script as a Home
Assistant number entity. Adjusting that entity rewrites the weight target
on the machine, so the next shot pulled with that script stops at the new
weight. You can also bind the number entity into automations — for
example, to step the target down by 0.5 g across a tasting flight, or to
expose a slider on a dashboard.

## Frontend card

For visualizing shot tracking data, check out [xenia-home-card](https://github.com/Knoedelauflauf/xenia-home-card).

## Removing the integration

1. In Home Assistant, go to **Settings → Devices & Services**.
2. Click the Xenia Espresso Machine integration card, open the three-dot
   menu, and choose **Delete**.
3. If you installed via HACS, open HACS, find Xenia Espresso Machine, and
   uninstall it. For manual installs, delete the
   `custom_components/xenia_home/` folder from your Home Assistant `config/`
   directory.
4. Restart Home Assistant.

The Xenia espresso machine itself stores no Home Assistant–specific data,
so no cleanup on the machine is necessary. If you previously enabled weight
management and let the integration create a new on-device script for you,
you may optionally delete that script from the machine's web UI. Recorded
entity history is kept by the Home Assistant recorder until it ages out of
the recorder's retention window or you purge it manually.
