"""Tests for xenia.py — the HTTP API client."""

from typing import Any

from aiohttp import ClientResponseError, ClientSession
from aioresponses import aioresponses as AioResponses
import pytest
from yarl import URL

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
from tests.fixtures.api_responses import (
    MACHINE_NEW_FW_FIELDS,
    MACHINE_PAYLOAD,
    OVERVIEW_NEW_FW_FIELDS,
    OVERVIEW_PAYLOAD,
)

HOST = "xenia.local"
BASE = f"http://{HOST}/api/v2"


@pytest.fixture
def mock_api():
    """Yield an aioresponses mock for use in xenia client tests."""
    with AioResponses() as m:
        yield m


@pytest.fixture
async def xenia(mock_api):
    """Yield a fresh Xenia client backed by a real ClientSession."""
    async with ClientSession() as session:
        yield Xenia(HOST, session)


# ===========================================================================
# _safe_int
# ===========================================================================


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (42, 42),
        ("7", 7),
        ("0", 0),
        (0, 0),
        (3.9, 3),
        ("3.0", None),
        (None, None),
        ("", None),
        ("abc", None),
        ([], None),
        ({}, None),
    ],
)
def test_safe_int(value: Any, expected: int | None) -> None:
    assert _safe_int(value) == expected


# ===========================================================================
# Enums
# ===========================================================================


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, MachineStatus.OFF),
        (1, MachineStatus.ON),
        (2, MachineStatus.ECO),
        (3, MachineStatus.BREWING),
        (4, MachineStatus.DRAINING),
        (99, MachineStatus.UNKNOWN),
    ],
)
def test_machine_status_values(value: int, expected: MachineStatus) -> None:
    assert MachineStatus(value) == expected
    assert str(expected) == expected.name


def test_machine_status_unknown_int_raises() -> None:
    with pytest.raises(ValueError):
        MachineStatus(55)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1, SteamBoilerStatus.OFF),
        (2, SteamBoilerStatus.ON),
        (99, SteamBoilerStatus.UNKNOWN),
    ],
)
def test_steam_boiler_status_values(value: int, expected: SteamBoilerStatus) -> None:
    assert SteamBoilerStatus(value) == expected


def test_steam_boiler_status_unknown_int_raises() -> None:
    with pytest.raises(ValueError):
        SteamBoilerStatus(0)


@pytest.mark.parametrize(
    ("control", "expected_int"),
    [
        (MachineControl.OFF, 0),
        (MachineControl.ON, 1),
        (MachineControl.ECO, 2),
        (MachineControl.SB_OFF, 3),
        (MachineControl.SB_ON, 4),
        (MachineControl.ON_SB_OFF, 5),
    ],
)
def test_machine_control_values(control: MachineControl, expected_int: int) -> None:
    assert int(control) == expected_int


# ===========================================================================
# Data classes (from_dict)
# ===========================================================================


def test_overview_data_from_full_dict() -> None:
    payload = {
        "MA_EXTRACTIONS": 100,
        "MA_STATUS": 1,
        "MA_CUR_PWR": 3.5,
        "BG_SENS_TEMP_A": 93.0,
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


@pytest.mark.parametrize(
    ("status_value", "expected"),
    [
        (0, MachineStatus.OFF),
        (2, MachineStatus.ECO),
        (3, MachineStatus.BREWING),
        (4, MachineStatus.DRAINING),
        (55, MachineStatus.UNKNOWN),
    ],
)
def test_overview_data_status_mapping(status_value, expected) -> None:
    data = XeniaOverviewData.from_dict({"MA_STATUS": status_value})
    assert data.ma_status == expected


def test_overview_data_casts_strings_to_float() -> None:
    data = XeniaOverviewData.from_dict({"MA_CUR_PWR": "3", "BG_SENS_TEMP_A": "90"})
    assert isinstance(data.ma_cur_pwr, float)
    assert isinstance(data.bg_sens_temp_a, float)


def test_overview_single_data_from_full_dict() -> None:
    payload = {
        "BG_SET_TEMP": 93.5,
        "PU_SENS_WATER_TANK_LEVEL": 1,
        "MA_MAC": "AA:BB:CC:DD:EE:FF",
        "POP_UP": 5,
    }
    data = XeniaOverviewSingleData.from_dict(payload)
    assert data.bg_set_temp == 93.5
    assert data.ma_mac == "AA:BB:CC:DD:EE:FF"
    assert data.pop_up == 5
    assert data.pu_sens_water_tank_level == 1


def test_overview_single_data_pop_up_defaults_to_none() -> None:
    data = XeniaOverviewSingleData.from_dict({})
    assert data.pop_up is None
    assert data.ma_mac == ""


def test_machine_data_from_full_dict() -> None:
    payload = {
        "MA_TYPE": 1,
        "FW_VERSION_MAJOR": 2,
        "FW_VERSION_MINOR": 3,
        "ESP_FW_MAJOR": 1,
        "ESP_FW_MINOR": 5,
    }
    data = XeniaMachineData.from_dict(payload)
    assert data.ma_type == 1
    assert data.fw_version() == "2.3"
    assert data.esp_fw_version() == "1.5"


def test_machine_data_fw_version_missing_part_returns_none() -> None:
    assert XeniaMachineData.from_dict({"FW_VERSION_MAJOR": 2}).fw_version() is None
    assert XeniaMachineData.from_dict({"FW_VERSION_MINOR": 3}).fw_version() is None
    assert XeniaMachineData.from_dict({}).fw_version() is None


def test_machine_data_fw_version_zero_values_are_valid() -> None:
    data = XeniaMachineData.from_dict({"FW_VERSION_MAJOR": 0, "FW_VERSION_MINOR": 0})
    assert data.fw_version() == "0.0"


def test_machine_data_bad_type_defaults_to_none() -> None:
    assert XeniaMachineData.from_dict({"MA_TYPE": "bad"}).ma_type is None


def test_overview_new_firmware_fields_parsed() -> None:
    data = XeniaOverviewData.from_dict({**OVERVIEW_PAYLOAD, **OVERVIEW_NEW_FW_FIELDS})
    assert data.pu_sens_scale_rate == 1.27


def test_overview_old_firmware_fields_are_none() -> None:
    data = XeniaOverviewData.from_dict(OVERVIEW_PAYLOAD)
    assert data.pu_sens_scale_rate is None


def test_overview_unparseable_new_field_is_none() -> None:
    data = XeniaOverviewData.from_dict({**OVERVIEW_PAYLOAD, "PU_SENS_SCALE_RATE": ""})
    assert data.pu_sens_scale_rate is None


def test_machine_serial_number_parsed() -> None:
    data = XeniaMachineData.from_dict({**MACHINE_PAYLOAD, **MACHINE_NEW_FW_FIELDS})
    assert data.ma_sn == "300200000000"


def test_machine_serial_number_absent_or_empty_is_none() -> None:
    assert XeniaMachineData.from_dict(MACHINE_PAYLOAD).ma_sn is None
    assert XeniaMachineData.from_dict({**MACHINE_PAYLOAD, "MA_SN": ""}).ma_sn is None


# ===========================================================================
# Xenia HTTP methods — happy paths
# ===========================================================================


async def test_device_connected_true_when_ma_status_present(mock_api, xenia) -> None:
    mock_api.get(f"{BASE}/overview", payload={"MA_STATUS": 1})
    assert await xenia.device_connected() is True


async def test_device_connected_false_when_ma_status_absent(mock_api, xenia) -> None:
    mock_api.get(f"{BASE}/overview", payload={"OTHER_KEY": 1})
    assert await xenia.device_connected() is False


async def test_device_connected_false_on_empty_response(mock_api, xenia) -> None:
    mock_api.get(f"{BASE}/overview", payload={})
    assert await xenia.device_connected() is False


async def test_device_connected_false_on_http_error(mock_api, xenia) -> None:
    mock_api.get(f"{BASE}/overview", status=404)
    assert await xenia.device_connected() is False


async def test_device_connected_false_on_network_error(mock_api, xenia) -> None:
    mock_api.get(f"{BASE}/overview", exception=OSError("connection refused"))
    assert await xenia.device_connected() is False


async def test_get_overview_parses_response(mock_api, xenia) -> None:
    mock_api.get(
        f"{BASE}/overview",
        payload={"MA_STATUS": 1, "MA_EXTRACTIONS": 99, "SB_STATUS": 2},
    )
    data = await xenia.get_overview()
    assert data.ma_status == MachineStatus.ON
    assert data.ma_extractions == 99
    assert data.sb_status == SteamBoilerStatus.ON


async def test_get_overview_raises_on_http_error(mock_api, xenia) -> None:
    mock_api.get(f"{BASE}/overview", status=503)
    with pytest.raises(ClientResponseError):
        await xenia.get_overview()


async def test_get_overview_single_parses_response(mock_api, xenia) -> None:
    mock_api.get(
        f"{BASE}/overview_single",
        payload={"BG_SET_TEMP": 95.0, "MA_MAC": "DE:AD:BE:EF:00:01"},
    )
    data = await xenia.get_overview_single()
    assert data.bg_set_temp == 95.0
    assert data.ma_mac == "DE:AD:BE:EF:00:01"


async def test_get_machine_parses_response(mock_api, xenia) -> None:
    mock_api.get(
        f"{BASE}/machine",
        payload={"MA_TYPE": 1, "FW_VERSION_MAJOR": 2, "FW_VERSION_MINOR": 3},
    )
    data = await xenia.get_machine()
    assert data.ma_type == 1
    assert data.fw_version() == "2.3"


# ===========================================================================
# Control endpoints — verify the sent payload
# ===========================================================================


async def test_machine_turn_on_with_steam_sends_on(mock_api, xenia) -> None:
    mock_api.post(f"{BASE}/machine/control", status=200)
    await xenia.machine_turn_on(sb_on=True)
    body = str(_last_post_body(mock_api, f"{BASE}/machine/control"))
    assert '"1"' in body  # MachineControl.ON


async def test_machine_turn_on_without_steam_sends_on_sb_off(mock_api, xenia) -> None:
    mock_api.post(f"{BASE}/machine/control", status=200)
    await xenia.machine_turn_on(sb_on=False)
    body = str(_last_post_body(mock_api, f"{BASE}/machine/control"))
    assert '"5"' in body  # MachineControl.ON_SB_OFF


async def test_machine_turn_off_sends_off(mock_api, xenia) -> None:
    mock_api.post(f"{BASE}/machine/control", status=200)
    await xenia.machine_turn_off()
    body = str(_last_post_body(mock_api, f"{BASE}/machine/control"))
    assert '"0"' in body


async def test_machine_set_eco_sends_eco(mock_api, xenia) -> None:
    mock_api.post(f"{BASE}/machine/control", status=200)
    await xenia.machine_set_eco()
    body = str(_last_post_body(mock_api, f"{BASE}/machine/control"))
    assert '"2"' in body


async def test_sb_turn_on_sends_true(mock_api, xenia) -> None:
    mock_api.post(f"{BASE}/toggle_sb", status=200)
    await xenia.sb_turn_on()
    body = str(_last_post_body(mock_api, f"{BASE}/toggle_sb"))
    assert "true" in body


async def test_sb_turn_off_sends_false(mock_api, xenia) -> None:
    mock_api.post(f"{BASE}/toggle_sb", status=200)
    await xenia.sb_turn_off()
    body = str(_last_post_body(mock_api, f"{BASE}/toggle_sb"))
    assert "false" in body


# ===========================================================================
# Temperature setters
# ===========================================================================


async def test_set_bg_set_temp_posts_value(mock_api, xenia) -> None:
    mock_api.post(f"{BASE}/inc_dec", payload={})
    await xenia.set_bg_set_temp(93.5)
    body = str(_last_post_body(mock_api, f"{BASE}/inc_dec"))
    assert "93.5" in body


async def test_set_bb_set_temp_posts_value(mock_api, xenia) -> None:
    mock_api.post(f"{BASE}/inc_dec_bb", payload={})
    await xenia.set_bb_set_temp(130.0)
    body = str(_last_post_body(mock_api, f"{BASE}/inc_dec_bb"))
    assert "130.0" in body


# ===========================================================================
# Scripts
# ===========================================================================


async def test_get_scripts_returns_id_title_dict(mock_api, xenia) -> None:
    mock_api.get(
        f"{BASE}/scripts/list",
        payload={"index_list": [10, 20], "title_list": ["MyShot", "Lungo"]},
    )
    assert await xenia.get_scripts() == {10: "MyShot", 20: "Lungo"}


async def test_get_scripts_empty_returns_empty(mock_api, xenia) -> None:
    mock_api.get(
        f"{BASE}/scripts/list",
        payload={"index_list": [], "title_list": []},
    )
    assert await xenia.get_scripts() == {}


async def test_get_scripts_missing_keys_returns_empty(mock_api, xenia) -> None:
    mock_api.get(f"{BASE}/scripts/list", payload={})
    assert await xenia.get_scripts() == {}


async def test_get_scripts_mismatched_lengths_zips_to_shortest(mock_api, xenia) -> None:
    mock_api.get(
        f"{BASE}/scripts/list",
        payload={"index_list": [1, 2, 3], "title_list": ["A", "B"]},
    )
    assert await xenia.get_scripts() == {1: "A", 2: "B"}


async def test_execute_script_sends_id(mock_api, xenia) -> None:
    mock_api.post(f"{BASE}/scripts/execute", status=200)
    await xenia.execute_script(42)
    body = str(_last_post_body(mock_api, f"{BASE}/scripts/execute"))
    assert "42" in body


async def test_execute_script_id_zero_sends_zero(mock_api, xenia) -> None:
    mock_api.post(f"{BASE}/scripts/execute", status=200)
    await xenia.execute_script(0)
    body = str(_last_post_body(mock_api, f"{BASE}/scripts/execute"))
    assert "0" in body


async def test_read_script_returns_content_and_title(mock_api, xenia) -> None:
    mock_api.post(
        f"{BASE}/scripts/read",
        payload={"Content": "1;13;3 70 5000;27 45;17;7;", "Title": "My Shot"},
    )
    result = await xenia.read_script(17)
    assert result["Content"] == "1;13;3 70 5000;27 45;17;7;"
    assert result["Title"] == "My Shot"


async def test_read_script_zero_pads_id(mock_api, xenia) -> None:
    mock_api.post(f"{BASE}/scripts/read", payload={})
    await xenia.read_script(5)
    body = str(_last_post_body(mock_api, f"{BASE}/scripts/read"))
    assert "005" in body


async def test_read_script_three_digit_id(mock_api, xenia) -> None:
    mock_api.post(f"{BASE}/scripts/read", payload={})
    await xenia.read_script(123)
    body = str(_last_post_body(mock_api, f"{BASE}/scripts/read"))
    assert "123" in body


async def test_create_script_sends_name_and_instruction(mock_api, xenia) -> None:
    mock_api.post(f"{BASE}/scripts/create", status=200)
    await xenia.create_script("My Espresso", "1;13;27 40;7;")
    body = str(_last_post_body(mock_api, f"{BASE}/scripts/create"))
    assert "My Espresso" in body
    assert "1;13;27 40;7;" in body


async def test_update_script_uses_edit_enabled(mock_api, xenia) -> None:
    mock_api.post(f"{BASE}/scripts/create", status=200)
    await xenia.update_script(5, "Name", "1;7;")
    body = str(_last_post_body(mock_api, f"{BASE}/scripts/create"))
    assert "Enabled" in body
    assert "5" in body


async def test_get_switches_returns_dict(mock_api, xenia) -> None:
    mock_api.get(
        f"{BASE}/switches",
        payload={"SWITCH_SET_LEFT_LEFT_0": 1, "SWITCH_SET_LEFT_LEFT_1": 2},
    )
    assert await xenia.get_switches() == {
        "SWITCH_SET_LEFT_LEFT_0": 1,
        "SWITCH_SET_LEFT_LEFT_1": 2,
    }


async def test_set_switch_preserves_other_keys(mock_api, xenia) -> None:
    mock_api.get(f"{BASE}/switches", payload={"KEY_A": 1, "KEY_B": 2})
    mock_api.post(f"{BASE}/switches", status=200)
    await xenia.set_switch("KEY_A", 99)
    body = str(_last_post_body(mock_api, f"{BASE}/switches"))
    assert "KEY_A" in body
    assert "99" in body
    assert "KEY_B" in body


# ===========================================================================
# All endpoints raise ClientResponseError on HTTP errors
# ===========================================================================


@pytest.mark.parametrize(
    ("method", "path", "kwargs", "callable_attr", "args"),
    [
        ("get", "overview", {}, "get_overview", ()),
        ("get", "overview_single", {}, "get_overview_single", ()),
        ("get", "machine", {}, "get_machine", ()),
        ("get", "scripts/list", {}, "get_scripts", ()),
        ("get", "switches", {}, "get_switches", ()),
        ("post", "scripts/execute", {}, "execute_script", (1,)),
        ("post", "scripts/read", {}, "read_script", (1,)),
        ("post", "scripts/create", {}, "create_script", ("name", "instr")),
        ("post", "scripts/create", {}, "update_script", (1, "name", "instr")),
    ],
)
async def test_http_500_raises(
    mock_api, xenia, method, path, kwargs, callable_attr, args
) -> None:
    register = getattr(mock_api, method)
    register(f"{BASE}/{path}", status=500)
    with pytest.raises(ClientResponseError):
        await getattr(xenia, callable_attr)(*args)


# ===========================================================================
# Endpoint URL verification — one parametrized test instead of 10
# ===========================================================================


@pytest.mark.parametrize(
    ("callable_attr", "args", "expected_path", "http_method"),
    [
        ("device_connected", (), "overview", "get"),
        ("get_overview", (), "overview", "get"),
        ("get_overview_single", (), "overview_single", "get"),
        ("get_machine", (), "machine", "get"),
        ("get_scripts", (), "scripts/list", "get"),
        ("get_switches", (), "switches", "get"),
        ("machine_turn_on", (), "machine/control", "post"),
        ("machine_turn_off", (), "machine/control", "post"),
        ("machine_set_eco", (), "machine/control", "post"),
        ("sb_turn_on", (), "toggle_sb", "post"),
        ("sb_turn_off", (), "toggle_sb", "post"),
        ("set_bg_set_temp", (90.0,), "inc_dec", "post"),
        ("set_bb_set_temp", (130.0,), "inc_dec_bb", "post"),
        ("execute_script", (1,), "scripts/execute", "post"),
        ("read_script", (1,), "scripts/read", "post"),
        ("create_script", ("n", "i"), "scripts/create", "post"),
        ("update_script", (1, "n", "i"), "scripts/create", "post"),
    ],
)
async def test_method_hits_expected_url(
    mock_api, xenia, callable_attr, args, expected_path, http_method
) -> None:
    url = f"{BASE}/{expected_path}"
    register = getattr(mock_api, http_method)
    # Default payload covers both GET-returning-json and POST-returning-status
    register(url, payload={"index_list": [], "title_list": []}, status=200)
    await getattr(xenia, callable_attr)(*args)
    key = (http_method.upper(), _yarl(url))
    assert key in mock_api.requests, f"{callable_attr} did not hit {url}"


# ===========================================================================
# Helpers
# ===========================================================================


def _yarl(url: str) -> URL:
    """Aioresponses keys requests by yarl.URL, not str."""
    return URL(url)


def _last_post_body(mock_api, url: str):
    """Return the `data=` body of the most recent POST to `url`."""
    key = ("POST", _yarl(url))
    calls = mock_api.requests.get(key)
    assert calls, f"No POST to {url} was made"
    return calls[-1].kwargs.get("data")
