"""Contract tests for the shot history WebSocket API."""

from typing import Any

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from tests import setup_second_machine
from tests.conftest import MockXeniaApi
from tests.fixtures.shots import shot_payload


async def _cmd(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    msg: dict[str, Any],
    **client_kwargs: Any,
) -> dict[str, Any]:
    client = await hass_ws_client(hass, **client_kwargs)
    await client.send_json_auto_id(msg)
    return await client.receive_json()


async def _seed(init_integration: MockConfigEntry, *payloads: dict[str, Any]) -> None:
    store = init_integration.runtime_data.shot_store
    for payload in payloads:
        await store.async_add_shot(payload)


async def test_list_returns_summaries_newest_first(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """shots/list returns summaries, newest first."""
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


async def test_list_filters_and_limits(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """shots/list filters by start time and limits the count; the bounds are exclusive."""
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


async def test_list_accepts_naive_timestamp(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """A bound without a time zone is read as UTC."""
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
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """An unparseable bound is rejected."""
    msg = await _cmd(
        hass,
        hass_ws_client,
        {"type": "xenia_home/shots/list", "after": "gestern"},
    )
    assert not msg["success"]
    assert msg["error"]["code"] == "invalid_format"


async def test_get_returns_full_payloads_in_request_order(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """shots/get returns full payloads in request order and skips unknown ids."""
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


async def test_unknown_entry_id_errors(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """An unknown entry_id is not found."""
    msg = await _cmd(
        hass,
        hass_ws_client,
        {"type": "xenia_home/shots/list", "entry_id": "deadbeef"},
    )
    assert not msg["success"]
    assert msg["error"]["code"] == "not_found"


async def test_multiple_entries_require_entry_id(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """With several machines a command has to name one."""
    second_entry, _ = await setup_second_machine(hass, mock_xenia_api)

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


async def test_delete_removes_shot_from_api(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """A deleted shot is gone from list and get."""
    keep = shot_payload("2026-07-01T10:00:00.000+00:00")
    drop = shot_payload("2026-07-02T10:00:00.000+00:00")
    await _seed(init_integration, keep, drop)

    msg = await _cmd(
        hass,
        hass_ws_client,
        {"type": "xenia_home/shots/delete", "shot_id": drop["start_time"]},
    )
    assert msg["success"]

    msg = await _cmd(hass, hass_ws_client, {"type": "xenia_home/shots/list"})
    assert [s["shot_id"] for s in msg["result"]["shots"]] == [keep["start_time"]]

    msg = await _cmd(
        hass,
        hass_ws_client,
        {
            "type": "xenia_home/shots/get",
            "shot_ids": [drop["start_time"], keep["start_time"]],
        },
    )
    assert [s["shot_id"] for s in msg["result"]["shots"]] == [keep["start_time"]]


async def test_no_loaded_entry_errors_on_every_command(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Every command fails while no machine is loaded."""
    await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()

    for msg in (
        {"type": "xenia_home/shots/list"},
        {
            "type": "xenia_home/shots/get",
            "shot_ids": ["2026-07-01T10:00:00.000+00:00"],
        },
        {
            "type": "xenia_home/shots/delete",
            "shot_id": "2026-07-01T10:00:00.000+00:00",
        },
    ):
        result = await _cmd(hass, hass_ws_client, msg)
        assert not result["success"]
        assert result["error"]["code"] == "not_found"


async def test_non_admin_can_read_but_not_delete(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    hass_read_only_access_token: str,
) -> None:
    """Users without admin rights can read shots but not delete them."""
    shot = shot_payload("2026-07-01T10:00:00.000+00:00")
    await _seed(init_integration, shot)
    token = hass_read_only_access_token
    msg = await _cmd(
        hass,
        hass_ws_client,
        {"type": "xenia_home/shots/delete", "shot_id": shot["start_time"]},
        access_token=token,
    )
    assert not msg["success"]
    assert msg["error"]["code"] == "unauthorized"
    msg = await _cmd(
        hass, hass_ws_client, {"type": "xenia_home/shots/list"}, access_token=token
    )
    assert [s["shot_id"] for s in msg["result"]["shots"]] == [shot["start_time"]]
    msg = await _cmd(
        hass,
        hass_ws_client,
        {"type": "xenia_home/shots/get", "shot_ids": [shot["start_time"]]},
        access_token=token,
    )
    assert msg["success"]


async def test_delete_unknown_shot_errors(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Deleting an unknown shot is not found."""
    msg = await _cmd(
        hass,
        hass_ws_client,
        {
            "type": "xenia_home/shots/delete",
            "shot_id": "2099-01-01T00:00:00.000+00:00",
        },
    )
    assert not msg["success"]
    assert msg["error"]["code"] == "not_found"
