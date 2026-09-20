"""HTTP API client and data classes for the Xenia espresso machine."""

from dataclasses import dataclass
from enum import IntEnum
import json
import logging
from typing import Any

from aiohttp import (
    ClientError,
    ClientPayloadError,
    ClientResponse,
    ClientResponseError,
    ClientSession,
    ClientTimeout,
)

_LOGGER = logging.getLogger(__name__)


class MachineControl(IntEnum):
    """Control codes accepted by `/api/v2/machine/control`."""

    OFF = 0
    ON = 1
    ECO = 2
    SB_OFF = 3
    SB_ON = 4
    ON_SB_OFF = 5

    def __str__(self):
        """Return the member name for logging."""
        return self.name


class MachineStatus(IntEnum):
    """Machine state reported in `MA_STATUS`."""

    OFF = 0
    ON = 1
    ECO = 2
    BREWING = 3
    DRAINING = 4
    UNKNOWN = 99

    def __str__(self):
        """Return the member name for logging."""
        return self.name


class SteamBoilerStatus(IntEnum):
    """Steam boiler state reported in `SB_STATUS`."""

    OFF = 1
    ON = 2
    UNKNOWN = 99

    def __str__(self):
        """Return the member name for logging."""
        return self.name


@dataclass
class XeniaOverviewData:
    """Decoded payload of `/api/v2/overview`."""

    ma_extractions: int
    ma_operating_hours: int
    ma_status: MachineStatus
    ma_clock: int
    ma_cur_pwr: float
    ma_max_pwr: int
    ma_energy_total_kwh: float
    bg_sens_temp_a: float
    bg_level_pw_control: int
    pu_sens_press: float
    pu_level_pw_control: int
    pu_set_level_pw_control: int
    pu_sens_flow_meter_ml: float
    sb_sens_press: float
    bb_sens_temp_a: float
    bb_level_pw_control: int
    sb_status: SteamBoilerStatus
    scale_weight: float
    pu_sens_scale_rate: float | None

    @staticmethod
    def from_dict(data: dict) -> XeniaOverviewData:
        """Build a `XeniaOverviewData` from a raw API dict."""
        try:
            machine_status_enum = MachineStatus(data.get("MA_STATUS", 99))
        except ValueError:
            machine_status_enum = MachineStatus.UNKNOWN
        try:
            sb_status_enum = SteamBoilerStatus(data.get("SB_STATUS", 99))
        except ValueError:
            sb_status_enum = SteamBoilerStatus.UNKNOWN
        return XeniaOverviewData(
            ma_extractions=data.get("MA_EXTRACTIONS", 0),
            ma_operating_hours=data.get("MA_OPERATING_HOURS", 0),
            ma_status=machine_status_enum,
            ma_clock=data.get("MA_CLOCK", 0),
            ma_cur_pwr=float(data.get("MA_CUR_PWR", 0.0)),
            ma_max_pwr=data.get("MA_MAX_PWR", 0),
            ma_energy_total_kwh=float(data.get("MA_ENERGY_TOTAL_KWH", 0.0)),
            bg_sens_temp_a=float(data.get("BG_SENS_TEMP_A", 0.0)),
            bg_level_pw_control=data.get("BG_LEVEL_PW_CONTROL", 0),
            pu_sens_press=float(data.get("PU_SENS_PRESS", 0.0)),
            pu_level_pw_control=data.get("PU_LEVEL_PW_CONTROL", 0),
            pu_set_level_pw_control=data.get("PU_SET_LEVEL_PW_CONTROL", 0),
            pu_sens_flow_meter_ml=float(data.get("PU_SENS_FLOW_METER_ML", 0.0)),
            sb_sens_press=float(data.get("SB_SENS_PRESS", 0.0)),
            bb_sens_temp_a=float(data.get("BB_SENS_TEMP_A", 0.0)),
            bb_level_pw_control=data.get("BB_LEVEL_PW_CONTROL", 0),
            sb_status=sb_status_enum,
            scale_weight=float(data.get("SCALE_WEIGHT", 0.0)),
            pu_sens_scale_rate=_optional_float(data, "PU_SENS_SCALE_RATE"),
        )


@dataclass
class XeniaOverviewSingleData:
    """Decoded payload of `/api/v2/overview_single`."""

    bg_set_temp: float
    pu_set_press: float
    pu_sens_water_tank_level: int
    sb_set_press: float
    bb_set_temp: float
    psp: int
    ma_mac: str
    ma_extractions_start: int
    pop_up: int | None

    @staticmethod
    def from_dict(data: dict) -> XeniaOverviewSingleData:
        """Build a `XeniaOverviewSingleData` from a raw API dict."""
        return XeniaOverviewSingleData(
            bg_set_temp=float(data.get("BG_SET_TEMP", 0.0)),
            pu_set_press=float(data.get("PU_SET_PRESS", 0.0)),
            pu_sens_water_tank_level=int(data.get("PU_SENS_WATER_TANK_LEVEL", 0)),
            sb_set_press=float(data.get("SB_SET_PRESS", 0.0)),
            bb_set_temp=float(data.get("BB_SET_TEMP", 0.0)),
            psp=int(data.get("PSP", 0)),
            ma_mac=data.get("MA_MAC", ""),
            ma_extractions_start=int(data.get("MA_EXTRACTIONS_START", 0)),
            # pop up is optional
            pop_up=data.get("POP_UP"),
        )


@dataclass
class XeniaMachineData:
    """Firmware and machine identification, from `/api/v2/machine`."""

    ma_type: int | None
    fw_version_major: int | None
    fw_version_minor: int | None
    esp_fw_major: int | None
    esp_fw_minor: int | None
    ma_sn: str | None

    @staticmethod
    def from_dict(data: dict) -> XeniaMachineData:
        """Build a `XeniaMachineData` from a raw API dict."""
        return XeniaMachineData(
            ma_type=_safe_int(data.get("MA_TYPE")),
            fw_version_major=_safe_int(data.get("FW_VERSION_MAJOR")),
            fw_version_minor=_safe_int(data.get("FW_VERSION_MINOR")),
            esp_fw_major=_safe_int(data.get("ESP_FW_MAJOR")),
            esp_fw_minor=_safe_int(data.get("ESP_FW_MINOR")),
            ma_sn=data.get("MA_SN") or None,
        )

    def fw_version(self) -> str | None:
        """Return the main firmware version as `major.minor`, or None if unknown."""
        if self.fw_version_major is None or self.fw_version_minor is None:
            return None
        return f"{self.fw_version_major}.{self.fw_version_minor}"

    def esp_fw_version(self) -> str | None:
        """Return the ESP firmware version as `major.minor`, or None if unknown."""
        if self.esp_fw_major is None or self.esp_fw_minor is None:
            return None
        return f"{self.esp_fw_major}.{self.esp_fw_minor}"


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except TypeError, ValueError:
        return None


def _optional_float(data: dict, key: str) -> float | None:
    if key not in data:
        return None
    try:
        return float(data[key])
    except TypeError, ValueError:
        return None


# The firmware answers an unknown path with a redirect to index.html, which
# followed would look like a success, so requests below send
# allow_redirects=False and any 3xx counts as an error.
def _raise_for_status(resp: ClientResponse) -> None:
    if resp.status >= 300:
        raise ClientResponseError(
            resp.request_info,
            resp.history,
            status=resp.status,
            headers=resp.headers,
            message=resp.reason or "",
        )


def _json(body: bytes) -> Any:
    """Decode a response body, turning bad JSON into a ClientError."""
    try:
        return json.loads(body)
    except ValueError as err:
        raise ClientPayloadError(f"Invalid JSON from the machine: {err}") from err


class Xenia:
    """Async HTTP client for the Xenia espresso machine local API (v2)."""

    def __init__(self, host: str, session: ClientSession) -> None:
        """Bind the client to a host and a shared aiohttp session."""
        self._host = host
        self._session = session

    async def device_connected(self) -> bool:
        """Return True if the machine answered with an `MA_STATUS` payload."""
        try:
            json_data = await self._get_overview_raw()
            if "MA_STATUS" in json_data:
                return True
        except (ClientError, OSError, TimeoutError) as e:
            _LOGGER.info("Connection test failed: %s", e)
            return False
        return False

    async def machine_turn_on(self, sb_on: bool = True):
        """Turn the machine on, optionally suppressing the steam boiler."""
        if sb_on:
            await self._control_machine(MachineControl.ON)
        else:
            await self._control_machine(MachineControl.ON_SB_OFF)

    async def machine_turn_off(self):
        """Turn the machine off."""
        await self._control_machine(MachineControl.OFF)

    async def machine_set_eco(self):
        """Switch the machine into eco mode."""
        await self._control_machine(MachineControl.ECO)

    async def sb_turn_on(self):
        """Turn the steam boiler on."""
        await self._toggle_sb(True)

    async def sb_turn_off(self):
        """Turn the steam boiler off."""
        await self._toggle_sb(False)

    async def _get(self, path: str, timeout: int = 10) -> bytes:
        url = f"http://{self._host}/api/v2/{path}"
        async with self._session.get(
            url,
            timeout=ClientTimeout(total=timeout),
            allow_redirects=False,
        ) as resp:
            _raise_for_status(resp)
            return await resp.read()

    async def _get_overview_raw(self) -> dict[str, Any]:
        return _json(await self._get("overview"))

    async def get_overview(self) -> XeniaOverviewData:
        """Fetch and decode the fast-changing overview payload."""
        return XeniaOverviewData.from_dict(await self._get_overview_raw())

    async def get_overview_single(self) -> XeniaOverviewSingleData:
        """Fetch and decode the setpoint / configuration overview payload."""
        return XeniaOverviewSingleData.from_dict(
            _json(await self._get("overview_single"))
        )

    async def get_machine(self) -> XeniaMachineData:
        """Fetch and decode the machine identification and firmware payload."""
        return XeniaMachineData.from_dict(_json(await self._get("machine")))

    async def _post(self, path: str, data: str, timeout: int = 5) -> bytes:
        url = f"http://{self._host}/api/v2/{path}"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        async with self._session.post(
            url,
            data=data,
            headers=headers,
            timeout=ClientTimeout(total=timeout),
            allow_redirects=False,
        ) as resp:
            _raise_for_status(resp)
            return await resp.read()

    async def _control_machine(self, action: int) -> None:
        data = f'{{"action":"{int(action)}"}}'
        await self._post("machine/control", data)

    async def _toggle_sb(self, action: bool) -> None:
        data = f'{{"TOGGLE":{str(action).lower()},"SAVE":true}}'
        await self._post("toggle/sb", data)

    async def set_bg_set_temp(self, value: float) -> None:
        """Set the brew-group target temperature in degrees Celsius."""
        data = f'{{"BG_SET_TEMP":"{value}", "BB_SET_TEMP":"{value}"}}'
        await self._post("inc_dec", data)

    async def set_bb_set_temp(self, value: float) -> None:
        """Set the brew-boiler target temperature in degrees Celsius."""
        data = f'{{"BB_SET_TEMP":"{value}"}}'
        await self._post("inc_dec_bb", data)

    async def get_scripts(self) -> dict[int, str]:
        """Get available scripts as {id: title} dict."""
        data = _json(await self._get("scripts/list"))
        index_list = data.get("index_list", [])
        title_list = data.get("title_list", [])
        return dict(zip(index_list, title_list, strict=False))

    async def execute_script(self, script_id: int) -> None:
        """Execute a script by ID."""
        data = f'{{"ID":{script_id}}}'
        await self._post("scripts/execute", data)

    async def stop_script(self) -> None:
        """Stop the currently running script."""
        await self._get("scripts/stop")

    async def get_switches(self) -> dict[str, int]:
        """Get switch-to-script mappings."""
        return _json(await self._get("switches"))

    async def read_script(self, script_id: int) -> dict[str, str]:
        """Read a script's content by ID.

        Returns dict with 'Content' (instruction) and 'Title' keys.
        """
        file_name = f"{script_id:03d}"
        data = f'{{"FILE_NAME":"{file_name}"}}'
        return _json(await self._post("scripts/read", data, timeout=10))

    async def create_script(self, name: str, instruction: str) -> None:
        """Create a new script on the machine."""
        data = (
            '{"script_id":null,"Edit":"Disabled","switch":null,'
            f'"script":"none","name":"{name}","instruction":"{instruction}"}}'
        )
        await self._post("scripts/create", data)

    async def update_script(self, script_id: int, name: str, instruction: str) -> None:
        """Update an existing script on the machine."""
        data = (
            f'{{"script_id":{script_id},"Edit":"Enabled","switch":null,'
            f'"script":"none","name":"{name}","instruction":"{instruction}"}}'
        )
        await self._post("scripts/create", data)

    async def set_switch(self, switch_key: str, script_id: int) -> None:
        """Set a switch to trigger a specific script."""
        # Fetch current switches, update the one key, and send all back
        current = await self.get_switches()
        current[switch_key] = script_id
        # Convert all values to strings as per API format
        data = "{" + ",".join(f'"{k}":"{v}"' for k, v in current.items()) + "}"
        await self._post("switches", data)
