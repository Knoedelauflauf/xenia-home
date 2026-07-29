"""Contract tests for the shot history WebSocket API."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xenia_home.const import XENIA_DOMAIN
from tests.conftest import MockXeniaApi
from tests.fixtures.shots import shot_payload


@pytest.fixture(autouse=True)
def _allow_ws_loopback(mock_xenia_api):
    """hass_ws_client's real localhost connection must bypass aioresponses,
    which otherwise intercepts every aiohttp request while its mock is active.
    """
    mock_xenia_api._mock._passthrough.append("http://127.0.0.1")


async def _cmd(hass, hass_ws_client, msg):
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(msg)
    return await client.receive_json()


async def _seed(init_integration, *payloads):
    store = init_integration.runtime_data.shot_store
    for payload in payloads:
        await store.async_add_shot(payload)


async def test_list_returns_summaries_newest_first(
    hass, init_integration, hass_ws_client
):
    early = shot_payload("2026-06-15T08:00:00.000+00:00")
    late = shot_payload("2026-07-01T10:00:00.000+00:00")
    await _seed(init_integration, early, late)

    msg = await _cmd(hass, hass_ws_client, {"type": "xenia_home/shots/list"})
    assert msg["success"]
    shots = msg["result"]["shots"]
    assert [s["shot_id"] for s in shots] == [late["start_time"], early["start_time"]]
    assert shots[0] == {
        "shot_id": late["start_time"],
        "start_time": late["start_time"],
        "brew_end_time": late["brew_end_time"],
        "duration_seconds": late["duration_seconds"],
        "final_weight_g": late["weights"][-1],
    }


async def test_list_filters_and_limits(hass, init_integration, hass_ws_client):
    a = shot_payload("2026-07-01T10:00:00.000+00:00")
    b = shot_payload("2026-07-02T10:00:00.000+00:00")
    c = shot_payload("2026-07-03T10:00:00.000+00:00")
    await _seed(init_integration, a, b, c)

    msg = await _cmd(
        hass,
        hass_ws_client,
        {
            # lenient input parsing: no milliseconds, Z suffix
            "type": "xenia_home/shots/list",
            "after": "2026-07-01T10:00:00Z",
            "before": "2026-07-03T10:00:00Z",
        },
    )
    assert [s["shot_id"] for s in msg["result"]["shots"]] == [b["start_time"]]

    msg = await _cmd(
        hass, hass_ws_client, {"type": "xenia_home/shots/list", "limit": 2}
    )
    assert [s["shot_id"] for s in msg["result"]["shots"]] == [
        c["start_time"],
        b["start_time"],
    ]


async def test_list_accepts_naive_timestamp(hass, init_integration, hass_ws_client):
    a = shot_payload("2026-07-01T10:00:00.000+00:00")
    b = shot_payload("2026-07-02T10:00:00.000+00:00")
    await _seed(init_integration, a, b)

    msg = await _cmd(
        hass,
        hass_ws_client,
        {"type": "xenia_home/shots/list", "after": "2026-07-01T12:00:00"},
    )
    assert msg["success"]
    assert [s["shot_id"] for s in msg["result"]["shots"]] == [b["start_time"]]


async def test_list_rejects_unparseable_timestamp(
    hass, init_integration, hass_ws_client
):
    msg = await _cmd(
        hass,
        hass_ws_client,
        {"type": "xenia_home/shots/list", "after": "gestern"},
    )
    assert not msg["success"]
    assert msg["error"]["code"] == "invalid_timestamp"


async def test_get_returns_full_payloads_in_request_order(
    hass, init_integration, hass_ws_client
):
    a = shot_payload("2026-07-01T10:00:00.000+00:00")
    b = shot_payload("2026-07-02T10:00:00.000+00:00")
    await _seed(init_integration, a, b)

    msg = await _cmd(
        hass,
        hass_ws_client,
        {
            "type": "xenia_home/shots/get",
            "shot_ids": [
                b["start_time"],
                "2099-01-01T00:00:00.000+00:00",
                a["start_time"],
            ],
        },
    )
    assert msg["success"]
    shots = msg["result"]["shots"]
    assert [s["shot_id"] for s in shots] == [b["start_time"], a["start_time"]]
    assert shots[1] == {**a, "shot_id": a["start_time"]}


async def test_unknown_entry_id_errors(hass, init_integration, hass_ws_client):
    msg = await _cmd(
        hass,
        hass_ws_client,
        {"type": "xenia_home/shots/list", "entry_id": "deadbeef"},
    )
    assert not msg["success"]
    assert msg["error"]["code"] == "entry_not_found"


async def test_multiple_entries_require_entry_id(
    hass, init_integration, mock_xenia_api, hass_ws_client
):
    second_api = MockXeniaApi(mock_xenia_api._mock, "xenia2.local")
    second_api.register()
    second_entry = MockConfigEntry(
        domain=XENIA_DOMAIN,
        title="xenia2.local",
        unique_id="xenia2.local",
        data={"host": "xenia2.local"},
        options={},
    )
    second_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(second_entry.entry_id)
    await hass.async_block_till_done()

    msg = await _cmd(hass, hass_ws_client, {"type": "xenia_home/shots/list"})
    assert not msg["success"]
    assert msg["error"]["code"] == "multiple_entries"

    msg = await _cmd(
        hass,
        hass_ws_client,
        {"type": "xenia_home/shots/list", "entry_id": second_entry.entry_id},
    )
    assert msg["success"]
    assert msg["result"]["shots"] == []
