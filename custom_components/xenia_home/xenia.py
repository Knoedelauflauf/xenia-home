"""HTTP API client and data classes for the Xenia espresso machine."""

from dataclasses import dataclass
from enum import IntEnum
import json
from typing import Any

from aiohttp import (
    ClientPayloadError,
    ClientResponse,
    ClientResponseError,
    ClientSession,
    ClientTimeout,
)


class MachineControl(IntEnum):
    """Control codes accepted by `/api/v2/machine/control`."""

    OFF = 0
    ON = 1
    ECO = 2
    ON_SB_OFF = 5


class MachineStatus(IntEnum):
    """Machine state reported in `MA_STATUS`."""

    OFF = 0
    ON = 1
    ECO = 2
    BREWING = 3
    DRAINING = 4
    UNKNOWN = 99


ACTIVE_STATUSES = frozenset(
    {MachineStatus.ON, MachineStatus.BREWING, MachineStatus.DRAINING}
)


class SteamBoilerStatus(IntEnum):
    """Steam boiler state reported in `SB_STATUS`."""

    OFF = 1
    ON = 2
    UNKNOWN = 99


@dataclass
class XeniaOverviewData:
    """Decoded payload of `/api/v2/overview`."""

    ma_extractions: int | None
    ma_operating_hours: int | None
    ma_status: MachineStatus
    ma_clock: int | None
    ma_cur_pwr: float | None
    ma_max_pwr: int | None
    ma_energy_total_kwh: float | None
    bg_sens_temp_a: float | None
    bg_level_pw_control: int | None
    pu_sens_press: float | None
    pu_level_pw_control: int | None
    pu_set_level_pw_control: int | None
    pu_sens_flow_meter_ml: float | None
    sb_sens_press: float | None
    bb_sens_temp_a: float | None
    bb_level_pw_control: int | None
    sb_status: SteamBoilerStatus
    scale_weight: float | None
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
            ma_extractions=_safe_int(data.get("MA_EXTRACTIONS")),
            ma_operating_hours=_safe_int(data.get("MA_OPERATING_HOURS")),
            ma_status=machine_status_enum,
            ma_clock=_safe_int(data.get("MA_CLOCK")),
            ma_cur_pwr=_safe_float(data.get("MA_CUR_PWR")),
            ma_max_pwr=_safe_int(data.get("MA_MAX_PWR")),
            ma_energy_total_kwh=_safe_float(data.get("MA_ENERGY_TOTAL_KWH")),
            bg_sens_temp_a=_safe_float(data.get("BG_SENS_TEMP_A")),
            bg_level_pw_control=_safe_int(data.get("BG_LEVEL_PW_CONTROL")),
            pu_sens_press=_safe_float(data.get("PU_SENS_PRESS")),
            pu_level_pw_control=_safe_int(data.get("PU_LEVEL_PW_CONTROL")),
            pu_set_level_pw_control=_safe_int(data.get("PU_SET_LEVEL_PW_CONTROL")),
            pu_sens_flow_meter_ml=_safe_float(data.get("PU_SENS_FLOW_METER_ML")),
            sb_sens_press=_safe_float(data.get("SB_SENS_PRESS")),
            bb_sens_temp_a=_safe_float(data.get("BB_SENS_TEMP_A")),
            bb_level_pw_control=_safe_int(data.get("BB_LEVEL_PW_CONTROL")),
            sb_status=sb_status_enum,
            scale_weight=_safe_float(data.get("SCALE_WEIGHT")),
            pu_sens_scale_rate=_safe_float(data.get("PU_SENS_SCALE_RATE")),
        )


@dataclass
class XeniaOverviewSingleData:
    """Decoded payload of `/api/v2/overview_single`."""

    bg_set_temp: float | None
    pu_set_press: float | None
    pu_sens_water_tank_level: int | None
    sb_set_press: float | None
    bb_set_temp: float | None
    psp: int | None
    ma_mac: str
    ma_extractions_start: int | None
    pop_up: int | None

    @staticmethod
    def from_dict(data: dict) -> XeniaOverviewSingleData:
        """Build a `XeniaOverviewSingleData` from a raw API dict."""
        return XeniaOverviewSingleData(
            bg_set_temp=_safe_float(data.get("BG_SET_TEMP")),
            pu_set_press=_safe_float(data.get("PU_SET_PRESS")),
            pu_sens_water_tank_level=_safe_int(data.get("PU_SENS_WATER_TANK_LEVEL")),
            sb_set_press=_safe_float(data.get("SB_SET_PRESS")),
            bb_set_temp=_safe_float(data.get("BB_SET_TEMP")),
            psp=_safe_int(data.get("PSP")),
            ma_mac=data.get("MA_MAC", ""),
            ma_extractions_start=_safe_int(data.get("MA_EXTRACTIONS_START")),
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
    try:
        return int(value)
    except TypeError, ValueError:
        return None


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except TypeError, ValueError:
        return None


def _raise_for_status(resp: ClientResponse) -> None:
    """Raise a ClientResponseError for anything but a 2xx status."""
    # The firmware answers an unknown path with a redirect to index.html, which
    # followed would look like a success, so callers send allow_redirects=False
    # and any 3xx counts as an error.
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


def _script_body(script_id: int | None, name: str, instruction: str) -> str:
    return json.dumps(
        {
            "script_id": script_id,
            "Edit": "Disabled" if script_id is None else "Enabled",
            "switch": None,
            "script": "none",
            "name": name,
            "instruction": instruction,
        },
        separators=(",", ":"),
        ensure_ascii=False,
    )


class Xenia:
    """Async HTTP client for the Xenia espresso machine local API (v2)."""

    def __init__(self, host: str, session: ClientSession) -> None:
        """Bind the client to a host and a shared aiohttp session."""
        self._host = host
        self._session = session

    async def get_mac(self) -> str:
        """Fetch the MAC address, which every firmware reports."""
        payload = _json(await self._get("overview_single"))
        if isinstance(payload, dict) and (mac := payload.get("MA_MAC")):
            return str(mac)
        raise ClientPayloadError("The machine reported no MAC address")

    async def machine_turn_on(self, sb_on: bool) -> None:
        """Turn the machine on, optionally suppressing the steam boiler."""
        if sb_on:
            await self._control_machine(MachineControl.ON)
        else:
            await self._control_machine(MachineControl.ON_SB_OFF)

    async def machine_turn_off(self) -> None:
        """Turn the machine off."""
        await self._control_machine(MachineControl.OFF)

    async def machine_set_eco(self) -> None:
        """Switch the machine into eco mode."""
        await self._control_machine(MachineControl.ECO)

    async def sb_turn_on(self) -> None:
        """Turn the steam boiler on."""
        await self._toggle_sb(True)

    async def sb_turn_off(self) -> None:
        """Turn the steam boiler off."""
        await self._toggle_sb(False)

    def _url(self, path: str) -> str:
        return f"http://{self._host}/api/v2/{path}"

    async def _get(self, path: str, timeout: int = 10) -> bytes:
        async with self._session.get(
            self._url(path),
            timeout=ClientTimeout(total=timeout),
            allow_redirects=False,
        ) as resp:
            _raise_for_status(resp)
            return await resp.read()

    async def get_overview(self) -> XeniaOverviewData:
        """Fetch and decode the fast-changing overview payload."""
        return XeniaOverviewData.from_dict(_json(await self._get("overview")))

    async def get_overview_single(self) -> XeniaOverviewSingleData:
        """Fetch and decode the setpoint / configuration overview payload."""
        return XeniaOverviewSingleData.from_dict(
            _json(await self._get("overview_single"))
        )

    async def get_machine(self) -> XeniaMachineData:
        """Fetch and decode the machine identification and firmware payload."""
        return XeniaMachineData.from_dict(_json(await self._get("machine")))

    async def _post(self, path: str, data: str, timeout: int = 5) -> bytes:
        async with self._session.post(
            self._url(path),
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
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
        """Return the scripts as {id: title}."""
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

    async def tare_scale(self) -> None:
        """Tare the Bluetooth scale connected to the machine."""
        await self._post("scale/write", "{}")

    async def get_switches(self) -> dict[str, int]:
        """Return the switch settings, including the switch-to-script assignments."""
        switches: dict[str, int] = _json(await self._get("switches"))
        return switches

    async def read_script(self, script_id: int) -> dict[str, str]:
        """Return a script as {"Content": instruction, "Title": title}."""
        file_name = f"{script_id:03d}"
        data = f'{{"FILE_NAME":"{file_name}"}}'
        script: dict[str, str] = _json(
            await self._post("scripts/read", data, timeout=10)
        )
        return script

    async def create_script(self, name: str, instruction: str) -> None:
        """Create a new script on the machine."""
        await self._post("scripts/create", _script_body(None, name, instruction))

    async def update_script(self, script_id: int, name: str, instruction: str) -> None:
        """Update an existing script on the machine."""
        await self._post("scripts/create", _script_body(script_id, name, instruction))

    async def set_switch(self, switch_key: str, script_id: int) -> None:
        """Assign a script to a switch."""
        current = {
            k: v
            for k, v in (await self.get_switches()).items()
            if k.startswith("SWITCH_SET_")
        }
        current[switch_key] = script_id
        data = "{" + ",".join(f'"{k}":"{v}"' for k, v in current.items()) + "}"
        await self._post("switches", data)
