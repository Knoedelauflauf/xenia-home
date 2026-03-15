# Xenia Home

> [!IMPORTANT]
> This project is an unofficial Home Assistant integration for controlling and monitoring espresso machines produced by Xenia Espresso GmbH.
> It is **not affiliated with, endorsed by, or supported by Xenia Espresso GmbH** in any way.
> All product and company names, trademarks, and registered trademarks are the property of their respective owners.
> Use of names or trademarks in this project is solely for identification purposes to indicate device compatibility.
> This software is provided "as is", without any warranty. Use at your own risk.

Home Assistant integration for Xenia espresso machines.

## Installation

- Install as a custom repository via HACS
- Or manually download and extract to the `custom_components` directory

Once installed, use Add Integration → Xenia Espresso Machine.

## Features

- Power on/off, ECO mode, steam boiler control
- Temperature setpoints (brew group & brew boiler)
- Sensors: temperatures, pressures, energy, extraction counter, operating hours
- Water tank level monitoring
- Script execution (service call by ID or name)
- Physical switch configuration (map each switch position to a script)
- Shot tracking with temperature, pressure, flow rate, and weight data
- Script weight management: adjust the brew weight target directly from Home Assistant

### Weight management

The integration can manage the weight target of a script on your Xenia machine. This allows you to change the target brew weight from Home Assistant without using the machine's web UI.

To enable, go to the integration's options (Configure) and enable weight management. You can select an existing script that contains a weight target or create a new one. The weight target number entity will appear and lets you adjust the final brew weight in grams.

## Frontend card

For visualizing shot tracking data, check out [xenia-home-card](https://github.com/Knoedelauflauf/xenia-home-card).

## Compatibility

- Xenia DBL with API v2
- Other models may work but are untested
