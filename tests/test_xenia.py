"""Tests for the HTTP API client of the machine."""

import asyncio
from collections.abc import AsyncIterator
import json

from aiohttp import ClientError, ClientResponseError
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.xenia_home.xenia import Xenia

from tests.conftest import MockXeniaApi


@pytest.fixture
async def xenia(
    aioclient_mock: AiohttpClientMocker, mock_xenia_api: MockXeniaApi
) -> AsyncIterator[Xenia]:
    """Return a client for the fake machine."""
    session = aioclient_mock.create_session(asyncio.get_running_loop())
    yield Xenia(mock_xenia_api.host, session)
    await session.close()


async def test_get_mac(xenia: Xenia) -> None:
    """The MAC address comes from overview_single."""
    assert await xenia.get_mac() == "AA:BB:CC:DD:EE:FF"


@pytest.mark.parametrize(
    "fault",
    [
        {"json": {"OTHER_KEY": 1}},
        {"json": {"MA_MAC": ""}},
        {"json": ["MA_MAC"]},
        {"status": 404},
        {"exc": OSError("connection refused")},
    ],
)
async def test_get_mac_fails_without_a_mac(
    xenia: Xenia, mock_xenia_api: MockXeniaApi, fault: dict
) -> None:
    """A payload without a MAC address or a failed request raises a ClientError."""
    mock_xenia_api.override("get", "overview_single", **fault)
    with pytest.raises((ClientError, OSError)):
        await xenia.get_mac()


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {"index_list": [10, 20], "title_list": ["MyShot", "Lungo"]},
            {10: "MyShot", 20: "Lungo"},
        ),
        ({"index_list": [1, 2, 3], "title_list": ["A", "B"]}, {1: "A", 2: "B"}),
        ({}, {}),
    ],
)
async def test_get_scripts(
    xenia: Xenia, mock_xenia_api: MockXeniaApi, payload: dict, expected: dict
) -> None:
    """The script list pairs ids with titles."""
    mock_xenia_api.override("get", "scripts/list", json=payload)
    assert await xenia.get_scripts() == expected


@pytest.mark.parametrize(
    ("call", "path", "body"),
    [
        (lambda x: x.machine_turn_on(sb_on=True), "machine/control", '{"action":"1"}'),
        (lambda x: x.machine_turn_on(sb_on=False), "machine/control", '{"action":"5"}'),
        (lambda x: x.machine_turn_off(), "machine/control", '{"action":"0"}'),
        (lambda x: x.machine_set_eco(), "machine/control", '{"action":"2"}'),
        (lambda x: x.sb_turn_on(), "toggle/sb", '{"TOGGLE":true,"SAVE":true}'),
        (lambda x: x.sb_turn_off(), "toggle/sb", '{"TOGGLE":false,"SAVE":true}'),
        (
            lambda x: x.set_bg_set_temp(93.5),
            "inc_dec",
            '{"BG_SET_TEMP":"93.5", "BB_SET_TEMP":"93.5"}',
        ),
        (lambda x: x.set_bb_set_temp(130.0), "inc_dec_bb", '{"BB_SET_TEMP":"130.0"}'),
        (lambda x: x.execute_script(42), "scripts/execute", '{"ID":42}'),
        (
            lambda x: x.create_script("My Espresso", "1;13;27 40;7;"),
            "scripts/create",
            '{"script_id":null,"Edit":"Disabled","switch":null,"script":"none",'
            '"name":"My Espresso","instruction":"1;13;27 40;7;"}',
        ),
        (
            lambda x: x.update_script(5, "Name", "1;7;"),
            "scripts/create",
            '{"script_id":5,"Edit":"Enabled","switch":null,"script":"none",'
            '"name":"Name","instruction":"1;7;"}',
        ),
        (
            lambda x: x.update_script(5, 'Kaffee "Crème" \\ 1', "1;7;"),
            "scripts/create",
            '{"script_id":5,"Edit":"Enabled","switch":null,"script":"none",'
            '"name":"Kaffee \\"Crème\\" \\\\ 1","instruction":"1;7;"}',
        ),
    ],
)
async def test_writes(
    xenia: Xenia, mock_xenia_api: MockXeniaApi, call, path: str, body: str
) -> None:
    """Every write posts the body format the firmware expects."""
    await call(xenia)
    assert mock_xenia_api.bodies("post", path) == [body]


async def test_stop_script(xenia: Xenia, mock_xenia_api: MockXeniaApi) -> None:
    """Stopping a script is a GET."""
    await xenia.stop_script()
    assert len(mock_xenia_api.bodies("get", "scripts/stop")) == 1


@pytest.mark.parametrize(("script_id", "file_name"), [(5, "005"), (123, "123")])
async def test_read_script(
    xenia: Xenia, mock_xenia_api: MockXeniaApi, script_id: int, file_name: str
) -> None:
    """A script is read by its zero padded file name."""
    mock_xenia_api.set_script(script_id, "1;13;27 45;7;", "My Shot")
    assert await xenia.read_script(script_id) == {
        "Content": "1;13;27 45;7;",
        "Title": "My Shot",
    }
    assert mock_xenia_api.bodies("post", "scripts/read") == [
        f'{{"FILE_NAME":"{file_name}"}}'
    ]


async def test_set_switch_sends_only_switch_assignments(
    xenia: Xenia, mock_xenia_api: MockXeniaApi
) -> None:
    """Assigning a switch posts all assignments, but none of the other settings."""
    mock_xenia_api.override(
        "get",
        "switches",
        json={
            "SWITCH_SET_LEFT_LEFT_0": 1,
            "SWITCH_SET_RIGHT_RIGHT_1": 2,
            "MA_BEVERAGE_WEIGHT_DBL_INT_SCALE": 36,
            "MA_SET_TIMER_POWERDOWN": 10,
            "VIEW": 0,
        },
    )
    await xenia.set_switch("SWITCH_SET_LEFT_LEFT_0", 99)
    [body] = mock_xenia_api.bodies("post", "switches")
    assert json.loads(body) == {
        "SWITCH_SET_LEFT_LEFT_0": "99",
        "SWITCH_SET_RIGHT_RIGHT_1": "2",
    }


@pytest.mark.parametrize(
    ("method", "path", "call"),
    [
        ("get", "overview", lambda x: x.get_overview()),
        ("get", "overview_single", lambda x: x.get_overview_single()),
        ("get", "machine", lambda x: x.get_machine()),
        ("get", "scripts/list", lambda x: x.get_scripts()),
        ("get", "switches", lambda x: x.get_switches()),
        ("get", "scripts/stop", lambda x: x.stop_script()),
        ("post", "scripts/execute", lambda x: x.execute_script(1)),
        ("post", "scripts/read", lambda x: x.read_script(1)),
        ("post", "scripts/create", lambda x: x.create_script("name", "instr")),
        ("post", "toggle/sb", lambda x: x.sb_turn_on()),
    ],
)
@pytest.mark.parametrize("status", [301, 500])
async def test_error_status_raises(
    xenia: Xenia,
    mock_xenia_api: MockXeniaApi,
    method: str,
    path: str,
    call,
    status: int,
) -> None:
    """Error statuses raise, and so do redirects, which the firmware sends for unknown paths."""
    mock_xenia_api.override(method, path, status=status, headers={"Location": "/"})
    with pytest.raises(ClientResponseError):
        await call(xenia)


async def test_invalid_json_raises_client_error(
    xenia: Xenia, mock_xenia_api: MockXeniaApi
) -> None:
    """A body that is not JSON raises a ClientError like a failed request."""
    mock_xenia_api.override("get", "overview", text="<html></html>")
    with pytest.raises(ClientError):
        await xenia.get_overview()
