"""Tests for the Xenia espresso machine integration."""

from datetime import timedelta
from typing import TYPE_CHECKING, Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_fire_time_changed_exact,
)
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.xenia_home.const import XENIA_DOMAIN

if TYPE_CHECKING:
    from tests.conftest import MockXeniaApi


async def setup_integration(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up the integration for `entry`."""
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def pass_seconds(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float
) -> None:
    """Let `seconds` pass and run what became due."""
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def run_for(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float
) -> None:
    """Let `seconds` pass in small steps, running each timer when it is due."""
    end = dt_util.utcnow() + timedelta(seconds=seconds)
    while dt_util.utcnow() < end:
        freezer.tick(0.01)
        async_fire_time_changed_exact(hass)
        await hass.async_block_till_done()


async def setup_second_machine(
    hass: HomeAssistant, mock_xenia_api: MockXeniaApi
) -> tuple[MockConfigEntry, MockXeniaApi]:
    """Set up a second machine on xenia2.local; return its entry and machine."""
    machine = mock_xenia_api.for_host("xenia2.local")
    machine.set_overview_single(MA_MAC="AA:BB:CC:DD:EE:01")
    entry = MockConfigEntry(
        domain=XENIA_DOMAIN,
        title="xenia2.local",
        unique_id="aa:bb:cc:dd:ee:01",
        minor_version=2,
        data={"host": "xenia2.local"},
    )
    await setup_integration(hass, entry)
    return entry, machine


async def ws_command(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    msg: dict[str, Any],
    **client_kwargs: Any,
) -> dict[str, Any]:
    """Send one websocket command and return the answer."""
    client = await hass_ws_client(hass, **client_kwargs)
    await client.send_json_auto_id(msg)
    answer: dict[str, Any] = await client.receive_json()
    return answer


async def listed_shots(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> list[dict[str, Any]]:
    """Return the shot summaries the websocket API lists, newest first."""
    answer = await ws_command(hass, hass_ws_client, {"type": "xenia_home/shots/list"})
    assert answer["success"]
    shots: list[dict[str, Any]] = answer["result"]["shots"]
    return shots


def stored_shots(entry_id: str, *payloads: dict[str, Any]) -> dict[str, Any]:
    """Return storage files holding `payloads`, in the format 0.7.0 writes."""
    files: dict[str, Any] = {}
    summaries = []
    for payload in payloads:
        shot_id = payload["start_time"]
        month = shot_id[:7]
        key = f"xenia_home/{entry_id}.shots_{month}"
        chunk = files.setdefault(
            key, {"version": 1, "minor_version": 1, "key": key, "data": {}}
        )
        chunk["data"][shot_id] = payload
        summaries.append(
            {
                "shot_id": shot_id,
                "start_time": shot_id,
                "brew_end_time": payload["brew_end_time"],
                "duration_seconds": payload["duration_seconds"],
                "final_weight_g": payload["weights"][-1],
                "month": month,
            }
        )
    files[f"xenia_home/{entry_id}.shots_index"] = {
        "version": 1,
        "minor_version": 1,
        "key": f"xenia_home/{entry_id}.shots_index",
        "data": {"migrated": True, "shots": summaries},
    }
    return files
