"""Unit tests for xenia.py — API client and data models."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import ClientResponseError, ClientSession, RequestInfo

from custom_components.xenia_home.xenia import (
    MachineControl,
    MachineStatus,
    SteamBoilerStatus,
    Xenia,
    XeniaMachineData,
    XeniaOverviewData,
    XeniaOverviewSingleData,
    _safe_int,
)


# ===========================================================================
# _safe_int
# ===========================================================================


@pytest.mark.parametrize(
    "value, expected",
    [
        (42, 42),
        ("7", 7),
        ("0", 0),
        (0, 0),
        (3.9, 3),
        ("3.0", None),  # float string cannot be cast to int directly
        (None, None),
        ("", None),
        ("abc", None),
        ([], None),
        ({}, None),
    ],
)
def test_safe_int_various_inputs(value: Any, expected: int | None) -> None:
    assert _safe_int(value) == expected


def test_safe_int_returns_none_for_none() -> None:
    assert _safe_int(None) is None


def test_safe_int_returns_none_for_unconvertable_string() -> None:
    assert _safe_int("not-a-number") is None


def test_safe_int_accepts_integer_zero() -> None:
    assert _safe_int(0) == 0


# ===========================================================================
# MachineStatus enum
# ===========================================================================


@pytest.mark.parametrize(
    "value, expected",
    [
        (0, MachineStatus.OFF),
        (1, MachineStatus.ON),
        (2, MachineStatus.ECO),
        (3, MachineStatus.BREWING),
        (4, MachineStatus.DRAINING),
        (99, MachineStatus.UNKNOWN),
    ],
)
def test_machine_status_known_values(value: int, expected: MachineStatus) -> None:
    assert MachineStatus(value) == expected


def test_machine_status_str_returns_name() -> None:
    assert str(MachineStatus.ON) == "ON"
    assert str(MachineStatus.BREWING) == "BREWING"


def test_machine_status_unknown_value_raises() -> None:
    with pytest.raises(ValueError):
        MachineStatus(55)


# ===========================================================================
# SteamBoilerStatus enum
# ===========================================================================


@pytest.mark.parametrize(
    "value, expected",
    [
        (1, SteamBoilerStatus.OFF),
        (2, SteamBoilerStatus.ON),
        (99, SteamBoilerStatus.UNKNOWN),
    ],
)
def test_steam_boiler_status_known_values(
    value: int, expected: SteamBoilerStatus
) -> None:
    assert SteamBoilerStatus(value) == expected


def test_steam_boiler_status_str_returns_name() -> None:
    assert str(SteamBoilerStatus.OFF) == "OFF"
    assert str(SteamBoilerStatus.ON) == "ON"


def test_steam_boiler_status_unknown_value_raises() -> None:
    with pytest.raises(ValueError):
        SteamBoilerStatus(0)


# ===========================================================================
# MachineControl enum
# ===========================================================================


@pytest.mark.parametrize(
    "control, expected_int",
    [
        (MachineControl.OFF, 0),
        (MachineControl.ON, 1),
        (MachineControl.ECO, 2),
        (MachineControl.SB_OFF, 3),
        (MachineControl.SB_ON, 4),
        (MachineControl.ON_SB_OFF, 5),
    ],
)
def test_machine_control_int_values(control: MachineControl, expected_int: int) -> None:
    assert int(control) == expected_int


def test_machine_control_str_returns_name() -> None:
    assert str(MachineControl.OFF) == "OFF"
    assert str(MachineControl.ON_SB_OFF) == "ON_SB_OFF"


# ===========================================================================
# XeniaOverviewData.from_dict
# ===========================================================================


def test_overview_data_from_full_dict() -> None:
    payload: dict[str, Any] = {
        "MA_EXTRACTIONS": 100,
        "MA_OPERATING_HOURS": 500,
        "MA_STATUS": 1,
        "MA_CLOCK": 0,
        "MA_CUR_PWR": 3.5,
        "MA_MAX_PWR": 16,
        "MA_ENERGY_TOTAL_KWH": 10.0,
        "BG_SENS_TEMP_A": 93.0,
        "BG_LEVEL_PW_CONTROL": 50,
        "PU_SENS_PRESS": 9.0,
        "PU_LEVEL_PW_CONTROL": 80,
        "PU_SET_LEVEL_PW_CONTROL": 80,
        "PU_SENS_FLOW_METER_ML": 5.0,
        "SB_SENS_PRESS": 1.1,
        "BB_SENS_TEMP_A": 130.0,
        "BB_LEVEL_PW_CONTROL": 60,
        "SB_STATUS": 2,
        "SCALE_WEIGHT": 18.0,
    }
    data = XeniaOverviewData.from_dict(payload)
    assert data.ma_extractions == 100
    assert data.ma_status == MachineStatus.ON
    assert data.sb_status == SteamBoilerStatus.ON
    assert data.bg_sens_temp_a == 93.0
    assert data.scale_weight == 18.0


def test_overview_data_from_empty_dict_uses_defaults() -> None:
    data = XeniaOverviewData.from_dict({})
    assert data.ma_extractions == 0
    assert data.ma_status == MachineStatus.UNKNOWN
    assert data.sb_status == SteamBoilerStatus.UNKNOWN
    assert data.bg_sens_temp_a == 0.0
    assert data.scale_weight == 0.0
    assert data.ma_cur_pwr == 0.0
    assert data.ma_energy_total_kwh == 0.0


def test_overview_data_unknown_ma_status_maps_to_unknown() -> None:
    data = XeniaOverviewData.from_dict({"MA_STATUS": 42})
    assert data.ma_status == MachineStatus.UNKNOWN


def test_overview_data_unknown_sb_status_maps_to_unknown() -> None:
    data = XeniaOverviewData.from_dict({"SB_STATUS": 42})
    assert data.sb_status == SteamBoilerStatus.UNKNOWN


@pytest.mark.parametrize(
    "status_value, expected",
    [
        (0, MachineStatus.OFF),
        (2, MachineStatus.ECO),
        (3, MachineStatus.BREWING),
        (4, MachineStatus.DRAINING),
        (99, MachineStatus.UNKNOWN),
        (55, MachineStatus.UNKNOWN),
    ],
)
def test_overview_data_ma_status_all_known_values(
    status_value: int, expected: MachineStatus
) -> None:
    data = XeniaOverviewData.from_dict({"MA_STATUS": status_value})
    assert data.ma_status == expected


def test_overview_data_numeric_fields_cast_to_float() -> None:
    data = XeniaOverviewData.from_dict({"MA_CUR_PWR": "3", "BG_SENS_TEMP_A": "90"})
    assert isinstance(data.ma_cur_pwr, float)
    assert isinstance(data.bg_sens_temp_a, float)


# ===========================================================================
# XeniaOverviewSingleData.from_dict
# ===========================================================================


def test_overview_single_data_from_full_dict() -> None:
    payload: dict[str, Any] = {
        "BG_SET_TEMP": 93.5,
        "PU_SET_PRESS": 9.0,
        "PU_SENS_WATER_TANK_LEVEL": 1,
        "SB_SET_PRESS": 1.5,
        "BB_SET_TEMP": 130.0,
        "PSP": 0,
        "MA_MAC": "AA:BB:CC:DD:EE:FF",
        "MA_EXTRACTIONS_START": 100,
        "POP_UP": 5,
    }
    data = XeniaOverviewSingleData.from_dict(payload)
    assert data.bg_set_temp == 93.5
    assert data.ma_mac == "AA:BB:CC:DD:EE:FF"
    assert data.pop_up == 5
    assert data.pu_sens_water_tank_level == 1


def test_overview_single_data_popup_defaults_to_none() -> None:
    data = XeniaOverviewSingleData.from_dict({})
    assert data.pop_up is None


def test_overview_single_data_from_empty_dict_uses_defaults() -> None:
    data = XeniaOverviewSingleData.from_dict({})
    assert data.bg_set_temp == 0.0
    assert data.pu_sens_water_tank_level == 0
    assert data.ma_mac == ""
    assert data.psp == 0


def test_overview_single_data_popup_present_returns_value() -> None:
    data = XeniaOverviewSingleData.from_dict({"POP_UP": 99})
    assert data.pop_up == 99


# ===========================================================================
# XeniaMachineData.from_dict
# ===========================================================================


def test_machine_data_from_full_dict() -> None:
    payload: dict[str, Any] = {
        "MA_TYPE": 1,
        "FW_VERSION_MAJOR": 2,
        "FW_VERSION_MINOR": 3,
        "ESP_FW_MAJOR": 1,
        "ESP_FW_MINOR": 5,
    }
    data = XeniaMachineData.from_dict(payload)
    assert data.ma_type == 1
    assert data.fw_version_major == 2
    assert data.fw_version_minor == 3
    assert data.esp_fw_major == 1
    assert data.esp_fw_minor == 5


def test_machine_data_from_empty_dict_all_none() -> None:
    data = XeniaMachineData.from_dict({})
    assert data.ma_type is None
    assert data.fw_version_major is None
    assert data.fw_version_minor is None
    assert data.esp_fw_major is None
    assert data.esp_fw_minor is None


def test_machine_data_fw_version_both_present() -> None:
    data = XeniaMachineData.from_dict({"FW_VERSION_MAJOR": 2, "FW_VERSION_MINOR": 3})
    assert data.fw_version() == "2.3"


def test_machine_data_fw_version_major_missing_returns_none() -> None:
    data = XeniaMachineData.from_dict({"FW_VERSION_MINOR": 3})
    assert data.fw_version() is None


def test_machine_data_fw_version_minor_missing_returns_none() -> None:
    data = XeniaMachineData.from_dict({"FW_VERSION_MAJOR": 2})
    assert data.fw_version() is None


def test_machine_data_fw_version_both_missing_returns_none() -> None:
    data = XeniaMachineData.from_dict({})
    assert data.fw_version() is None


def test_machine_data_esp_fw_version_both_present() -> None:
    data = XeniaMachineData.from_dict({"ESP_FW_MAJOR": 1, "ESP_FW_MINOR": 5})
    assert data.esp_fw_version() == "1.5"


def test_machine_data_esp_fw_version_major_missing_returns_none() -> None:
    data = XeniaMachineData.from_dict({"ESP_FW_MINOR": 5})
    assert data.esp_fw_version() is None


def test_machine_data_esp_fw_version_minor_missing_returns_none() -> None:
    data = XeniaMachineData.from_dict({"ESP_FW_MAJOR": 1})
    assert data.esp_fw_version() is None


def test_machine_data_fw_version_zero_values_are_valid() -> None:
    data = XeniaMachineData.from_dict({"FW_VERSION_MAJOR": 0, "FW_VERSION_MINOR": 0})
    assert data.fw_version() == "0.0"


def test_machine_data_with_unconvertable_type_defaults_to_none() -> None:
    data = XeniaMachineData.from_dict({"MA_TYPE": "bad"})
    assert data.ma_type is None


# ===========================================================================
# Xenia API client — helper to build mock context manager responses
# ===========================================================================


def _make_mock_response(json_data: Any, status: int = 200) -> MagicMock:
    """Build a mock aiohttp response context manager."""
    resp = AsyncMock()
    resp.json = AsyncMock(return_value=json_data)
    resp.raise_for_status = MagicMock()
    resp.status = status

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _make_error_response(status: int = 500) -> MagicMock:
    """Build a mock response that raises on raise_for_status."""
    resp = AsyncMock()
    request_info = MagicMock(spec=RequestInfo)
    resp.raise_for_status = MagicMock(
        side_effect=ClientResponseError(request_info, (), status=status)
    )
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# ===========================================================================
# Xenia.device_connected
# ===========================================================================


@pytest.mark.asyncio
async def test_device_connected_returns_true_when_ma_status_present() -> None:
    session = MagicMock(spec=ClientSession)
    session.get = MagicMock(return_value=_make_mock_response({"MA_STATUS": 1}))
    xenia = Xenia("xenia.local", session)
    result = await xenia.device_connected()
    assert result is True


@pytest.mark.asyncio
async def test_device_connected_returns_false_when_ma_status_absent() -> None:
    session = MagicMock(spec=ClientSession)
    session.get = MagicMock(return_value=_make_mock_response({"OTHER_KEY": 1}))
    xenia = Xenia("xenia.local", session)
    result = await xenia.device_connected()
    assert result is False


@pytest.mark.asyncio
async def test_device_connected_returns_false_on_exception() -> None:
    session = MagicMock(spec=ClientSession)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(side_effect=OSError("connection refused"))
    ctx.__aexit__ = AsyncMock(return_value=False)
    session.get = MagicMock(return_value=ctx)
    xenia = Xenia("xenia.local", session)
    result = await xenia.device_connected()
    assert result is False


@pytest.mark.asyncio
async def test_device_connected_returns_false_on_http_error() -> None:
    session = MagicMock(spec=ClientSession)
    session.get = MagicMock(return_value=_make_error_response(404))
    xenia = Xenia("xenia.local", session)
    result = await xenia.device_connected()
    assert result is False


@pytest.mark.asyncio
async def test_device_connected_returns_false_on_empty_response() -> None:
    session = MagicMock(spec=ClientSession)
    session.get = MagicMock(return_value=_make_mock_response({}))
    xenia = Xenia("xenia.local", session)
    result = await xenia.device_connected()
    assert result is False


# ===========================================================================
# Xenia.get_overview
# ===========================================================================


@pytest.mark.asyncio
async def test_get_overview_parses_response() -> None:
    payload = {"MA_STATUS": 1, "MA_EXTRACTIONS": 99, "SB_STATUS": 2}
    session = MagicMock(spec=ClientSession)
    session.get = MagicMock(return_value=_make_mock_response(payload))
    xenia = Xenia("xenia.local", session)
    data = await xenia.get_overview()
    assert data.ma_status == MachineStatus.ON
    assert data.ma_extractions == 99
    assert data.sb_status == SteamBoilerStatus.ON


@pytest.mark.asyncio
async def test_get_overview_raises_on_http_error() -> None:
    session = MagicMock(spec=ClientSession)
    session.get = MagicMock(return_value=_make_error_response(503))
    xenia = Xenia("xenia.local", session)
    with pytest.raises(ClientResponseError):
        await xenia.get_overview()


@pytest.mark.asyncio
async def test_get_overview_uses_correct_url() -> None:
    session = MagicMock(spec=ClientSession)
    session.get = MagicMock(return_value=_make_mock_response({}))
    xenia = Xenia("192.168.1.100", session)
    await xenia.get_overview()
    call_url = session.get.call_args[0][0]
    assert call_url == "http://192.168.1.100/api/v2/overview"


# ===========================================================================
# Xenia.get_overview_single
# ===========================================================================


@pytest.mark.asyncio
async def test_get_overview_single_parses_response() -> None:
    payload = {"BG_SET_TEMP": 95.0, "MA_MAC": "DE:AD:BE:EF:00:01"}
    session = MagicMock(spec=ClientSession)
    session.get = MagicMock(return_value=_make_mock_response(payload))
    xenia = Xenia("xenia.local", session)
    data = await xenia.get_overview_single()
    assert data.bg_set_temp == 95.0
    assert data.ma_mac == "DE:AD:BE:EF:00:01"


@pytest.mark.asyncio
async def test_get_overview_single_raises_on_http_error() -> None:
    session = MagicMock(spec=ClientSession)
    session.get = MagicMock(return_value=_make_error_response(500))
    xenia = Xenia("xenia.local", session)
    with pytest.raises(ClientResponseError):
        await xenia.get_overview_single()


@pytest.mark.asyncio
async def test_get_overview_single_uses_correct_url() -> None:
    session = MagicMock(spec=ClientSession)
    session.get = MagicMock(return_value=_make_mock_response({}))
    xenia = Xenia("myhost", session)
    await xenia.get_overview_single()
    call_url = session.get.call_args[0][0]
    assert call_url == "http://myhost/api/v2/overview_single"


# ===========================================================================
# Xenia.get_machine
# ===========================================================================


@pytest.mark.asyncio
async def test_get_machine_parses_response() -> None:
    payload = {"MA_TYPE": 1, "FW_VERSION_MAJOR": 2, "FW_VERSION_MINOR": 3}
    session = MagicMock(spec=ClientSession)
    session.get = MagicMock(return_value=_make_mock_response(payload))
    xenia = Xenia("xenia.local", session)
    data = await xenia.get_machine()
    assert data.ma_type == 1
    assert data.fw_version() == "2.3"


@pytest.mark.asyncio
async def test_get_machine_raises_on_http_error() -> None:
    session = MagicMock(spec=ClientSession)
    session.get = MagicMock(return_value=_make_error_response(503))
    xenia = Xenia("xenia.local", session)
    with pytest.raises(ClientResponseError):
        await xenia.get_machine()


@pytest.mark.asyncio
async def test_get_machine_uses_correct_url() -> None:
    session = MagicMock(spec=ClientSession)
    session.get = MagicMock(return_value=_make_mock_response({}))
    xenia = Xenia("myhost", session)
    await xenia.get_machine()
    call_url = session.get.call_args[0][0]
    assert call_url == "http://myhost/api/v2/machine"


# ===========================================================================
# Xenia._control_machine / machine_turn_on / machine_turn_off / machine_set_eco
# ===========================================================================


@pytest.mark.asyncio
async def test_machine_turn_on_with_steam_calls_correct_control() -> None:
    session = MagicMock(spec=ClientSession)
    resp = AsyncMock()
    resp.raise_for_status = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(return_value=ctx)
    xenia = Xenia("xenia.local", session)
    await xenia.machine_turn_on(sb_on=True)
    call_data = session.post.call_args[1]["data"]
    assert '"1"' in call_data  # MachineControl.ON = 1


@pytest.mark.asyncio
async def test_machine_turn_on_without_steam_calls_on_sb_off() -> None:
    session = MagicMock(spec=ClientSession)
    resp = AsyncMock()
    resp.raise_for_status = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(return_value=ctx)
    xenia = Xenia("xenia.local", session)
    await xenia.machine_turn_on(sb_on=False)
    call_data = session.post.call_args[1]["data"]
    assert '"5"' in call_data  # MachineControl.ON_SB_OFF = 5


@pytest.mark.asyncio
async def test_machine_turn_off_calls_off_control() -> None:
    session = MagicMock(spec=ClientSession)
    resp = AsyncMock()
    resp.raise_for_status = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(return_value=ctx)
    xenia = Xenia("xenia.local", session)
    await xenia.machine_turn_off()
    call_data = session.post.call_args[1]["data"]
    assert '"0"' in call_data  # MachineControl.OFF = 0


@pytest.mark.asyncio
async def test_machine_set_eco_calls_eco_control() -> None:
    session = MagicMock(spec=ClientSession)
    resp = AsyncMock()
    resp.raise_for_status = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(return_value=ctx)
    xenia = Xenia("xenia.local", session)
    await xenia.machine_set_eco()
    call_data = session.post.call_args[1]["data"]
    assert '"2"' in call_data  # MachineControl.ECO = 2


@pytest.mark.asyncio
async def test_control_machine_uses_correct_url() -> None:
    session = MagicMock(spec=ClientSession)
    resp = AsyncMock()
    resp.raise_for_status = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(return_value=ctx)
    xenia = Xenia("myhost", session)
    await xenia.machine_turn_off()
    call_url = session.post.call_args[0][0]
    assert call_url == "http://myhost/api/v2/machine/control"


# ===========================================================================
# Xenia._toggle_sb / sb_turn_on / sb_turn_off
# ===========================================================================


@pytest.mark.asyncio
async def test_sb_turn_on_sends_true() -> None:
    session = MagicMock(spec=ClientSession)
    resp = AsyncMock()
    resp.raise_for_status = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(return_value=ctx)
    xenia = Xenia("xenia.local", session)
    await xenia.sb_turn_on()
    call_data = session.post.call_args[1]["data"]
    assert "true" in call_data


@pytest.mark.asyncio
async def test_sb_turn_off_sends_false() -> None:
    session = MagicMock(spec=ClientSession)
    resp = AsyncMock()
    resp.raise_for_status = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(return_value=ctx)
    xenia = Xenia("xenia.local", session)
    await xenia.sb_turn_off()
    call_data = session.post.call_args[1]["data"]
    assert "false" in call_data


@pytest.mark.asyncio
async def test_toggle_sb_uses_correct_url() -> None:
    session = MagicMock(spec=ClientSession)
    resp = AsyncMock()
    resp.raise_for_status = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(return_value=ctx)
    xenia = Xenia("myhost", session)
    await xenia.sb_turn_on()
    call_url = session.post.call_args[0][0]
    assert call_url == "http://myhost/api/v2/toggle_sb"


# ===========================================================================
# Xenia.set_bg_set_temp / set_bb_set_temp
# ===========================================================================


@pytest.mark.asyncio
async def test_set_bg_set_temp_calls_inc_dec_with_correct_value() -> None:
    session = MagicMock(spec=ClientSession)
    resp = AsyncMock()
    resp.json = AsyncMock(return_value={})
    resp.raise_for_status = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(return_value=ctx)
    xenia = Xenia("xenia.local", session)
    await xenia.set_bg_set_temp(93.5)
    call_data = session.post.call_args[1]["data"]
    assert "93.5" in call_data


@pytest.mark.asyncio
async def test_set_bb_set_temp_calls_inc_dec_bb_with_correct_value() -> None:
    session = MagicMock(spec=ClientSession)
    resp = AsyncMock()
    resp.json = AsyncMock(return_value={})
    resp.raise_for_status = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(return_value=ctx)
    xenia = Xenia("xenia.local", session)
    await xenia.set_bb_set_temp(130.0)
    call_url = session.post.call_args[0][0]
    call_data = session.post.call_args[1]["data"]
    assert "inc_dec_bb" in call_url
    assert "130.0" in call_data


@pytest.mark.asyncio
async def test_set_bg_set_temp_uses_inc_dec_url() -> None:
    session = MagicMock(spec=ClientSession)
    resp = AsyncMock()
    resp.json = AsyncMock(return_value={})
    resp.raise_for_status = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(return_value=ctx)
    xenia = Xenia("myhost", session)
    await xenia.set_bg_set_temp(90.0)
    call_url = session.post.call_args[0][0]
    assert call_url == "http://myhost/api/v2/inc_dec"


# ===========================================================================
# Xenia.get_scripts
# ===========================================================================


@pytest.mark.asyncio
async def test_get_scripts_returns_id_title_dict() -> None:
    payload = {"index_list": [10, 20], "title_list": ["MyShot", "Lungo"]}
    session = MagicMock(spec=ClientSession)
    session.get = MagicMock(return_value=_make_mock_response(payload))
    xenia = Xenia("xenia.local", session)
    scripts = await xenia.get_scripts()
    assert scripts == {10: "MyShot", 20: "Lungo"}


@pytest.mark.asyncio
async def test_get_scripts_empty_lists_returns_empty_dict() -> None:
    payload = {"index_list": [], "title_list": []}
    session = MagicMock(spec=ClientSession)
    session.get = MagicMock(return_value=_make_mock_response(payload))
    xenia = Xenia("xenia.local", session)
    scripts = await xenia.get_scripts()
    assert scripts == {}


@pytest.mark.asyncio
async def test_get_scripts_missing_keys_returns_empty_dict() -> None:
    payload: dict = {}
    session = MagicMock(spec=ClientSession)
    session.get = MagicMock(return_value=_make_mock_response(payload))
    xenia = Xenia("xenia.local", session)
    scripts = await xenia.get_scripts()
    assert scripts == {}


@pytest.mark.asyncio
async def test_get_scripts_mismatched_lengths_zips_to_shortest() -> None:
    payload = {"index_list": [1, 2, 3], "title_list": ["A", "B"]}
    session = MagicMock(spec=ClientSession)
    session.get = MagicMock(return_value=_make_mock_response(payload))
    xenia = Xenia("xenia.local", session)
    scripts = await xenia.get_scripts()
    assert scripts == {1: "A", 2: "B"}


@pytest.mark.asyncio
async def test_get_scripts_raises_on_http_error() -> None:
    session = MagicMock(spec=ClientSession)
    session.get = MagicMock(return_value=_make_error_response(503))
    xenia = Xenia("xenia.local", session)
    with pytest.raises(ClientResponseError):
        await xenia.get_scripts()


@pytest.mark.asyncio
async def test_get_scripts_uses_correct_url() -> None:
    session = MagicMock(spec=ClientSession)
    session.get = MagicMock(
        return_value=_make_mock_response({"index_list": [], "title_list": []})
    )
    xenia = Xenia("myhost", session)
    await xenia.get_scripts()
    call_url = session.get.call_args[0][0]
    assert call_url == "http://myhost/api/v2/scripts/list"


# ===========================================================================
# Xenia.execute_script
# ===========================================================================


@pytest.mark.asyncio
async def test_execute_script_sends_correct_id() -> None:
    session = MagicMock(spec=ClientSession)
    resp = AsyncMock()
    resp.raise_for_status = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(return_value=ctx)
    xenia = Xenia("xenia.local", session)
    await xenia.execute_script(42)
    call_data = session.post.call_args[1]["data"]
    assert "42" in call_data


@pytest.mark.asyncio
async def test_execute_script_raises_on_http_error() -> None:
    session = MagicMock(spec=ClientSession)
    session.post = MagicMock(return_value=_make_error_response(500))
    xenia = Xenia("xenia.local", session)
    with pytest.raises(ClientResponseError):
        await xenia.execute_script(1)


@pytest.mark.asyncio
async def test_execute_script_uses_correct_url() -> None:
    session = MagicMock(spec=ClientSession)
    resp = AsyncMock()
    resp.raise_for_status = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(return_value=ctx)
    xenia = Xenia("myhost", session)
    await xenia.execute_script(1)
    call_url = session.post.call_args[0][0]
    assert call_url == "http://myhost/api/v2/scripts/execute"


@pytest.mark.asyncio
async def test_execute_script_id_zero_sends_zero() -> None:
    session = MagicMock(spec=ClientSession)
    resp = AsyncMock()
    resp.raise_for_status = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(return_value=ctx)
    xenia = Xenia("xenia.local", session)
    await xenia.execute_script(0)
    call_data = session.post.call_args[1]["data"]
    assert "0" in call_data


# ===========================================================================
# Xenia.get_switches
# ===========================================================================


@pytest.mark.asyncio
async def test_get_switches_returns_dict() -> None:
    payload = {"SWITCH_SET_LEFT_LEFT_0": 1, "SWITCH_SET_LEFT_LEFT_1": 2}
    session = MagicMock(spec=ClientSession)
    session.get = MagicMock(return_value=_make_mock_response(payload))
    xenia = Xenia("xenia.local", session)
    switches = await xenia.get_switches()
    assert switches == {"SWITCH_SET_LEFT_LEFT_0": 1, "SWITCH_SET_LEFT_LEFT_1": 2}


@pytest.mark.asyncio
async def test_get_switches_raises_on_http_error() -> None:
    session = MagicMock(spec=ClientSession)
    session.get = MagicMock(return_value=_make_error_response(500))
    xenia = Xenia("xenia.local", session)
    with pytest.raises(ClientResponseError):
        await xenia.get_switches()


@pytest.mark.asyncio
async def test_get_switches_uses_correct_url() -> None:
    session = MagicMock(spec=ClientSession)
    session.get = MagicMock(return_value=_make_mock_response({}))
    xenia = Xenia("myhost", session)
    await xenia.get_switches()
    call_url = session.get.call_args[0][0]
    assert call_url == "http://myhost/api/v2/switches"


# ===========================================================================
# Xenia.set_switch
# ===========================================================================


@pytest.mark.asyncio
async def test_set_switch_fetches_current_and_posts_updated() -> None:
    current_switches = {"SWITCH_SET_LEFT_LEFT_0": 1, "SWITCH_SET_LEFT_LEFT_1": 2}
    session = MagicMock(spec=ClientSession)

    # GET returns current state
    get_ctx = _make_mock_response(current_switches)
    session.get = MagicMock(return_value=get_ctx)

    # POST response
    resp = AsyncMock()
    resp.raise_for_status = MagicMock()
    post_ctx = MagicMock()
    post_ctx.__aenter__ = AsyncMock(return_value=resp)
    post_ctx.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(return_value=post_ctx)

    xenia = Xenia("xenia.local", session)
    await xenia.set_switch("SWITCH_SET_LEFT_LEFT_0", 10)

    # Verify the POST was called and the data includes the updated value
    assert session.post.called
    call_data = session.post.call_args[1]["data"]
    assert "SWITCH_SET_LEFT_LEFT_0" in call_data
    assert "10" in call_data


@pytest.mark.asyncio
async def test_set_switch_preserves_other_switches() -> None:
    current_switches = {"KEY_A": 1, "KEY_B": 2}
    session = MagicMock(spec=ClientSession)

    get_ctx = _make_mock_response(current_switches)
    session.get = MagicMock(return_value=get_ctx)

    resp = AsyncMock()
    resp.raise_for_status = MagicMock()
    post_ctx = MagicMock()
    post_ctx.__aenter__ = AsyncMock(return_value=resp)
    post_ctx.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(return_value=post_ctx)

    xenia = Xenia("xenia.local", session)
    await xenia.set_switch("KEY_A", 99)

    call_data = session.post.call_args[1]["data"]
    # KEY_B must still be in the payload
    assert "KEY_B" in call_data


@pytest.mark.asyncio
async def test_set_switch_raises_on_post_http_error() -> None:
    session = MagicMock(spec=ClientSession)
    session.get = MagicMock(return_value=_make_mock_response({"KEY": 1}))
    session.post = MagicMock(return_value=_make_error_response(500))
    xenia = Xenia("xenia.local", session)
    with pytest.raises(ClientResponseError):
        await xenia.set_switch("KEY", 5)


@pytest.mark.asyncio
async def test_set_switch_raises_on_get_http_error() -> None:
    session = MagicMock(spec=ClientSession)
    session.get = MagicMock(return_value=_make_error_response(503))
    xenia = Xenia("xenia.local", session)
    with pytest.raises(ClientResponseError):
        await xenia.set_switch("KEY", 5)


# ===========================================================================
# Xenia.read_script
# ===========================================================================


@pytest.mark.asyncio
async def test_read_script_returns_content_and_title() -> None:
    payload = {"Content": "1;13;3 70 5000;27 45;17;7;", "Title": "My Shot"}
    session = MagicMock(spec=ClientSession)
    session.post = MagicMock(return_value=_make_mock_response(payload))
    xenia = Xenia("xenia.local", session)
    result = await xenia.read_script(17)
    assert result["Content"] == "1;13;3 70 5000;27 45;17;7;"
    assert result["Title"] == "My Shot"


@pytest.mark.asyncio
async def test_read_script_sends_zero_padded_id() -> None:
    session = MagicMock(spec=ClientSession)
    session.post = MagicMock(return_value=_make_mock_response({}))
    xenia = Xenia("xenia.local", session)
    await xenia.read_script(5)
    call_data = session.post.call_args[1]["data"]
    assert "005" in call_data


@pytest.mark.asyncio
async def test_read_script_pads_three_digit_id() -> None:
    session = MagicMock(spec=ClientSession)
    session.post = MagicMock(return_value=_make_mock_response({}))
    xenia = Xenia("xenia.local", session)
    await xenia.read_script(123)
    call_data = session.post.call_args[1]["data"]
    assert "123" in call_data


@pytest.mark.asyncio
async def test_read_script_uses_correct_url() -> None:
    session = MagicMock(spec=ClientSession)
    session.post = MagicMock(return_value=_make_mock_response({}))
    xenia = Xenia("myhost", session)
    await xenia.read_script(1)
    call_url = session.post.call_args[0][0]
    assert call_url == "http://myhost/api/v2/scripts/read"


@pytest.mark.asyncio
async def test_read_script_raises_on_http_error() -> None:
    session = MagicMock(spec=ClientSession)
    session.post = MagicMock(return_value=_make_error_response(500))
    xenia = Xenia("xenia.local", session)
    with pytest.raises(ClientResponseError):
        await xenia.read_script(10)


# ===========================================================================
# Xenia.create_script
# ===========================================================================


@pytest.mark.asyncio
async def test_create_script_sends_name_and_instruction() -> None:
    session = MagicMock(spec=ClientSession)
    resp = AsyncMock()
    resp.raise_for_status = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(return_value=ctx)
    xenia = Xenia("xenia.local", session)
    await xenia.create_script("My Espresso", "1;13;27 40;7;")
    call_data = session.post.call_args[1]["data"]
    assert "My Espresso" in call_data
    assert "1;13;27 40;7;" in call_data


@pytest.mark.asyncio
async def test_create_script_uses_correct_url() -> None:
    session = MagicMock(spec=ClientSession)
    resp = AsyncMock()
    resp.raise_for_status = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(return_value=ctx)
    xenia = Xenia("myhost", session)
    await xenia.create_script("Test", "1;7;")
    call_url = session.post.call_args[0][0]
    assert call_url == "http://myhost/api/v2/scripts/create"


@pytest.mark.asyncio
async def test_create_script_raises_on_http_error() -> None:
    session = MagicMock(spec=ClientSession)
    session.post = MagicMock(return_value=_make_error_response(500))
    xenia = Xenia("xenia.local", session)
    with pytest.raises(ClientResponseError):
        await xenia.create_script("Test", "1;7;")


# ===========================================================================
# Xenia.update_script
# ===========================================================================


@pytest.mark.asyncio
async def test_update_script_sends_script_id_name_and_instruction() -> None:
    session = MagicMock(spec=ClientSession)
    resp = AsyncMock()
    resp.raise_for_status = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(return_value=ctx)
    xenia = Xenia("xenia.local", session)
    await xenia.update_script(17, "Updated Shot", "1;13;27 50;7;")
    call_data = session.post.call_args[1]["data"]
    assert "17" in call_data
    assert "Updated Shot" in call_data
    assert "1;13;27 50;7;" in call_data


@pytest.mark.asyncio
async def test_update_script_uses_edit_enabled() -> None:
    session = MagicMock(spec=ClientSession)
    resp = AsyncMock()
    resp.raise_for_status = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(return_value=ctx)
    xenia = Xenia("xenia.local", session)
    await xenia.update_script(5, "Name", "1;7;")
    call_data = session.post.call_args[1]["data"]
    assert "Enabled" in call_data


@pytest.mark.asyncio
async def test_update_script_uses_same_url_as_create() -> None:
    session = MagicMock(spec=ClientSession)
    resp = AsyncMock()
    resp.raise_for_status = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(return_value=ctx)
    xenia = Xenia("myhost", session)
    await xenia.update_script(1, "Name", "1;7;")
    call_url = session.post.call_args[0][0]
    assert call_url == "http://myhost/api/v2/scripts/create"


@pytest.mark.asyncio
async def test_update_script_raises_on_http_error() -> None:
    session = MagicMock(spec=ClientSession)
    session.post = MagicMock(return_value=_make_error_response(500))
    xenia = Xenia("xenia.local", session)
    with pytest.raises(ClientResponseError):
        await xenia.update_script(10, "Name", "1;7;")
