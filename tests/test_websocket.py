"""Contract tests for the shot history WebSocket API."""

from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from tests import (
    listed_shots,
    setup_integration,
    setup_second_machine,
    stored_shots,
    ws_command,
)
from tests.conftest import MockXeniaApi
from tests.fixtures.shots import shot_payload


@pytest.fixture
def seed(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    init_integration: MockConfigEntry,
) -> Callable[..., Awaitable[None]]:
    """Return a function that stores shots and reloads the entry to read them."""

    async def _seed(*payloads: dict[str, Any]) -> None:
        hass_storage.update(stored_shots(init_integration.entry_id, *payloads))
        await hass.config_entries.async_reload(init_integration.entry_id)
        await hass.async_block_till_done()

    return _seed


async def test_history_of_0_7_0_is_kept(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    mock_config_entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Shots stored by release 0.7.0 are listed and returned after an update."""
    june = shot_payload("2026-06-15T08:00:00.000+00:00")
    july = shot_payload("2026-07-01T10:00:00.000+00:00")
    hass_storage.update(stored_shots(mock_config_entry.entry_id, june, july))
    await setup_integration(hass, mock_config_entry)

    assert [s["shot_id"] for s in await listed_shots(hass, hass_ws_client)] == [
        july["start_time"],
        june["start_time"],
    ]
    msg = await ws_command(
        hass,
        hass_ws_client,
        {"type": "xenia_home/shots/get", "shot_ids": [june["start_time"]]},
    )
    assert msg["result"]["shots"] == [{**june, "shot_id": june["start_time"]}]


async def test_list_returns_summaries_newest_first(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    seed: Callable[..., Awaitable[None]],
    hass_ws_client: WebSocketGenerator,
) -> None:
    """shots/list returns summaries, newest first."""
    early = shot_payload("2026-06-15T08:00:00.000+00:00")
    late = shot_payload("2026-07-01T10:00:00.000+00:00")
    await seed(early, late)

    msg = await ws_command(hass, hass_ws_client, {"type": "xenia_home/shots/list"})
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
    seed: Callable[..., Awaitable[None]],
    hass_ws_client: WebSocketGenerator,
) -> None:
    """shots/list filters by start time and limits the count; the bounds are exclusive."""
    a = shot_payload("2026-07-01T10:00:00.000+00:00")
    b = shot_payload("2026-07-02T10:00:00.000+00:00")
    c = shot_payload("2026-07-03T10:00:00.000+00:00")
    await seed(a, b, c)

    msg = await ws_command(
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

    msg = await ws_command(
        hass, hass_ws_client, {"type": "xenia_home/shots/list", "limit": 2}
    )
    assert [s["shot_id"] for s in msg["result"]["shots"]] == [
        c["start_time"],
        b["start_time"],
    ]


async def test_list_accepts_naive_timestamp(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    seed: Callable[..., Awaitable[None]],
    hass_ws_client: WebSocketGenerator,
) -> None:
    """A bound without a time zone is read in the time zone of Home Assistant."""
    await hass.config.async_set_time_zone("Europe/Berlin")
    a = shot_payload("2026-07-01T10:00:00.000+00:00")
    b = shot_payload("2026-07-01T11:00:00.000+00:00")
    await seed(a, b)

    # 12:30 in Berlin is 10:30 UTC: only the second shot starts after it,
    # while reading the bound as UTC would exclude both.
    msg = await ws_command(
        hass,
        hass_ws_client,
        {"type": "xenia_home/shots/list", "after": "2026-07-01T12:30:00"},
    )
    assert msg["success"]
    assert [s["shot_id"] for s in msg["result"]["shots"]] == [b["start_time"]]


async def test_list_rejects_unparseable_timestamp(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """An unparseable bound is rejected."""
    msg = await ws_command(
        hass,
        hass_ws_client,
        {"type": "xenia_home/shots/list", "after": "gestern"},
    )
    assert not msg["success"]
    assert msg["error"]["code"] == "invalid_format"


async def test_get_returns_full_payloads_in_request_order(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    seed: Callable[..., Awaitable[None]],
    hass_ws_client: WebSocketGenerator,
) -> None:
    """shots/get returns full payloads in request order and skips unknown ids."""
    a = shot_payload("2026-07-01T10:00:00.000+00:00")
    b = shot_payload("2026-07-02T10:00:00.000+00:00")
    await seed(a, b)

    msg = await ws_command(
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
    msg = await ws_command(
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

    msg = await ws_command(hass, hass_ws_client, {"type": "xenia_home/shots/list"})
    assert not msg["success"]
    assert msg["error"]["code"] == "multiple_entries"

    msg = await ws_command(
        hass,
        hass_ws_client,
        {"type": "xenia_home/shots/list", "entry_id": second_entry.entry_id},
    )
    assert msg["success"]
    assert msg["result"]["shots"] == []


async def test_delete_removes_shot_from_api(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    seed: Callable[..., Awaitable[None]],
    hass_ws_client: WebSocketGenerator,
) -> None:
    """A deleted shot is gone from list and get."""
    keep = shot_payload("2026-07-01T10:00:00.000+00:00")
    drop = shot_payload("2026-07-02T10:00:00.000+00:00")
    await seed(keep, drop)

    msg = await ws_command(
        hass,
        hass_ws_client,
        {"type": "xenia_home/shots/delete", "shot_id": drop["start_time"]},
    )
    assert msg["success"]

    msg = await ws_command(hass, hass_ws_client, {"type": "xenia_home/shots/list"})
    assert [s["shot_id"] for s in msg["result"]["shots"]] == [keep["start_time"]]

    msg = await ws_command(
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
        result = await ws_command(hass, hass_ws_client, msg)
        assert not result["success"]
        assert result["error"]["code"] == "not_found"


async def test_non_admin_can_read_but_not_delete(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    seed: Callable[..., Awaitable[None]],
    hass_ws_client: WebSocketGenerator,
    hass_read_only_access_token: str,
) -> None:
    """Users without admin rights can read shots but not delete them."""
    shot = shot_payload("2026-07-01T10:00:00.000+00:00")
    await seed(shot)
    token = hass_read_only_access_token
    msg = await ws_command(
        hass,
        hass_ws_client,
        {"type": "xenia_home/shots/delete", "shot_id": shot["start_time"]},
        access_token=token,
    )
    assert not msg["success"]
    assert msg["error"]["code"] == "unauthorized"
    msg = await ws_command(
        hass, hass_ws_client, {"type": "xenia_home/shots/list"}, access_token=token
    )
    assert [s["shot_id"] for s in msg["result"]["shots"]] == [shot["start_time"]]
    msg = await ws_command(
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
    msg = await ws_command(
        hass,
        hass_ws_client,
        {
            "type": "xenia_home/shots/delete",
            "shot_id": "2099-01-01T00:00:00.000+00:00",
        },
    )
    assert not msg["success"]
    assert msg["error"]["code"] == "not_found"
