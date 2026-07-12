# Xenia Espresso Machine API Documentation

Documentation of the Xenia Espresso API based on  
https://www.xenia-espresso.de/api.html

## Base URL

```
http://{host}/api/v2/
```

## GET Endpoints

### `/api/v2/status`

Minimal status check.

**Response:**
```json
{"MA_STATUS": 0}
```

---

### `/api/v2/overview`

Comprehensive overview of all real-time sensor data.

**Response Parameters:**

| Parameter                 | Type   | Description                          |
| ------------------------- | ------ | ------------------------------------ |
| `MA_STATUS`               | uint8  | Machine status (see enum below)      |
| `MA_EXTRACTIONS`          | uint32 | Number of extractions                |
| `MA_OPERATING_HOURS`      | uint32 | Operating hours                      |
| `MA_CLOCK`                | uint32 | System clock                         |
| `MA_CUR_PWR`              | float  | Current power consumption (amperes)  |
| `MA_MAX_PWR`              | uint16 | Maximum amperes                      |
| `MA_ENERGY_TOTAL_KWH`     | float  | Total energy consumption in kWh      |
| `MA_LAST_EXTRACTION_ML`   | string | Last extraction volume               |
| `BG_SENS_TEMP_A`          | float  | Brew group temperature (sensor)      |
| `BG_LEVEL_PW_CONTROL`     | uint16 | Brew group PWM control               |
| `BB_SENS_TEMP_A`          | float  | Brew boiler temperature (sensor)     |
| `BB_LEVEL_PW_CONTROL`     | uint16 | Brew boiler PWM control              |
| `PU_SENS_PRESS`           | float  | Pump pressure (bar)                  |
| `PU_LEVEL_PW_CONTROL`     | uint16 | Pump PWM control                     |
| `PU_SET_LEVEL_PW_CONTROL` | uint16 | Pump target PWM                      |
| `PU_SENS_FLOW_METER_ML`   | float  | Flow meter reading (ml/s)            |
| `SB_SENS_PRESS`           | float  | Steam boiler pressure (bar)          |
| `SB_STATUS`               | uint8  | Steam boiler status (see enum below) |
| `SCALE_WEIGHT`            | float  | Scale weight (grams)                 |

---

### `/api/v2/overview_single`

Configuration values and setpoints.

**Response Parameters:**

| Parameter                  | Type     | Description                    |
| -------------------------- | -------- | ------------------------------ |
| `BG_SET_TEMP`              | float    | Brew group target temperature  |
| `BB_SET_TEMP`              | float    | Brew boiler target temperature |
| `PU_SET_PRESS`             | float    | Pump target pressure           |
| `SB_SET_PRESS`             | float    | Steam boiler target pressure   |
| `PU_SENS_WATER_TANK_LEVEL` | int      | Water tank level               |
| `MA_MAC`                   | string   | MAC address                    |
| `MA_EXTRACTIONS_START`     | int      | Extraction counter start value |
| `PSP`                      | int      | ?                              |
| `POP_UP`                   | int/null | Pop-up message (optional)      |

---

## POST Endpoints

### `/api/v2/machine/control`

Controls the machine state.

**Content-Type:** `application/x-www-form-urlencoded`

**Body:**

```json
{"action": "0"}
```

**Action Values:**

| Value | Meaning                                          |
| ----- | ------------------------------------------------ |
| `0`   | OFF – Turn machine off                           |
| `1`   | ON – Turn machine on (with steam boiler)         |
| `2`   | ECO – Enable ECO mode                            |
| `3`   | SB_OFF – Turn steam boiler off (legacy?)         |
| `4`   | SB_ON – Turn steam boiler on (legacy?)           |
| `5`   | ON_SB_OFF – Turn machine on without steam boiler |

---

### `/api/v2/toggle_sb`

Turns the steam boiler on or off.

**Content-Type:** `application/x-www-form-urlencoded`

**Body:**

```json
{"TOGGLE": true}
```

or

```json
{"TOGGLE": false}
```

---

### `/api/v2/inc_dec`

Sets brew group and brew boiler temperature simultaneously.

**Content-Type:** `application/x-www-form-urlencoded`

**Body:**

```json
{"BG_SET_TEMP": "93.0", "BB_SET_TEMP": "93.0"}
```

---

### `/api/v2/inc_dec_bb`

Sets only the brew boiler temperature.

**Content-Type:** `application/x-www-form-urlencoded`

**Body:**

```json
{"BB_SET_TEMP": "93.0"}
```

---

### `/api/v2/machine`

Returns machine hardware and firmware information.

**Method:** GET

**Response Parameters:**

| Parameter          | Type | Description            |
| ------------------ | ---- | ---------------------- |
| `MA_TYPE`          | int  | Machine type           |
| `FW_VERSION_MAJOR` | int  | Firmware major version |
| `FW_VERSION_MINOR` | int  | Firmware minor version |
| `ESP_FW_MAJOR`     | int  | ESP firmware major     |
| `ESP_FW_MINOR`     | int  | ESP firmware minor     |

---

### `/api/v2/scripts/list`

Returns all user-defined scripts.

**Method:** GET

**Response:**
```json
{
  "index_list": [10, 20],
  "title_list": ["MyShot", "Lungo"]
}
```

---

### `/api/v2/scripts/read`

Reads a script's content by ID.

**Method:** POST
**Content-Type:** `application/x-www-form-urlencoded`

**Body:**
```json
{"FILE_NAME": "010"}
```

The file name is the script ID zero-padded to 3 digits.

**Response:**
```json
{
  "Content": "1;13;3 70 5000;27 45;17;7;",
  "Title": "MyShot"
}
```

The `Content` field contains semicolon-separated script commands (see script instruction format below).

---

### `/api/v2/scripts/create`

Creates or updates a script.

**Method:** POST
**Content-Type:** `application/x-www-form-urlencoded`

**Create new script:**
```json
{
  "script_id": null,
  "Edit": "Disabled",
  "switch": null,
  "script": "none",
  "name": "My Script",
  "instruction": "1;13;27 40;7;"
}
```

**Update existing script:**
```json
{
  "script_id": 10,
  "Edit": "Enabled",
  "switch": null,
  "script": "none",
  "name": "My Script",
  "instruction": "1;13;27 45;7;"
}
```

---

### `/api/v2/scripts/execute`

Executes a script by ID.

**Method:** POST
**Content-Type:** `application/x-www-form-urlencoded`

**Body:**
```json
{"ID": 10}
```

---

### `/api/v2/switches`

**GET** — Returns switch-to-script mappings.

**Response:**
```json
{
  "SWITCH_SET_LEFT_LEFT_0": 1,
  "SWITCH_SET_LEFT_LEFT_1": 2
}
```

**POST** — Updates all switch mappings. Send the full set of switch assignments.

**Content-Type:** `application/x-www-form-urlencoded`

**Body:**
```json
{
  "SWITCH_SET_LEFT_LEFT_0": "10",
  "SWITCH_SET_LEFT_LEFT_1": "2"
}
```

---

## Script instruction format

Scripts are stored as semicolon-separated commands. Each command starts with a command ID followed by optional arguments separated by spaces.

Example: `1;13;3 70 5000;27 45;17;7;`

Every script starts with command `1` (script start) and ends with command `7` (script end).

| Command ID | Description (DE)              | Description (EN)             | Arguments                    |
| ---------- | ----------------------------- | ---------------------------- | ---------------------------- |
| 1          | Script start                  | Script start                 | none                         |
| 2          | Pumpe an                      | Pump on                      | none                         |
| 3          | Leistung Pumpe %              | Pump power %                 | power (%), duration (ms)     |
| 4          | Pumpendruck bar               | Pump pressure bar            | pressure (mbar), duration (ms) |
| 5          | Waage, Flussrate              | Scale, flow rate             | rate (ml/s), duration (ms)   |
| 6          | Pumpe aus                     | Pump off                     | none                         |
| 7          | Script end                    | Script end                   | none                         |
| 8          | Leistung Brühboiler %         | Brew boiler power %          | percent                      |
| 9          | Leistung Brühgruppe %         | Brew group power %           | percent                      |
| 12         | Warten                        | Wait                         | duration (ms)                |
| 13         | Bezugsventil öffnen           | Open brew valve              | none                         |
| 14         | Bezugsventil schließen        | Close brew valve             | none                         |
| 15         | Ablassventil öffnen           | Open drain valve             | none                         |
| 16         | Ablassventil schließen        | Close drain valve            | none                         |
| 17         | Entleeren & Beenden           | Drain and finish             | none                         |
| 20         | Signalton                     | Signal tone                  | count, duration (ms)         |
| 25         | Warten Solltemperatur °C      | Wait for target temperature  | temperature (°C)             |
| 27         | Waage, Gewicht                | Scale, weight target         | weight (g)                   |
| 28         | Eco-Modus aktivieren          | Activate ECO mode            | none                         |
| 29         | Brühdruckbegrenzung           | Brew pressure limit          | pressure (bar)               |
| 30         | Begrenzung Flussrate          | Flow rate limit              | rate (ml/s)                  |
| 31         | Solltemperatur wiederherstellen | Restore target temperature  | none                         |

A script can contain multiple weight target commands (command 27), for example a preinfusion target and a final brew target.

---

## Enums

### MachineStatus (`MA_STATUS`)

| Value | Status   | Description                    |
| ----- | -------- | ------------------------------ |
| 0     | OFF      | Machine is off                 |
| 1     | ON       | Machine is on and heating      |
| 2     | ECO      | ECO mode (standby, no heating) |
| 3     | BREWING  | Active extraction              |
| 4     | DRAINING | Draining / cooling down        |

---

### SteamBoilerStatus (`SB_STATUS`)

| Value | Status |
| ----- | ------ |
| 1     | OFF    |
| 2     | ON     |

---

## Undocumented Features

The following features exist on the machine but are not controllable via the API:

* **ECO timer**: Time until the machine automatically switches to ECO mode
* **Auto-off timer**: Automatic shutdown
* **Scheduler / schedules**: Automatic power on/off

These settings must be configured directly on the device.

---

## Example: Python API Call

```python
import aiohttp

async def turn_on_machine(host: str):
    url = f"http://{host}/api/v2/machine/control"
    data = '{"action":"1"}'
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=data, headers=headers) as resp:
            resp.raise_for_status()
```
