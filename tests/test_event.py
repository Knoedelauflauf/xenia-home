"""Tests for the shot tracker event entity."""

import re

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import WebSocketGenerator
from syrupy.assertion import SnapshotAssertion

from tests import listed_shots, run_for, ws_command
from tests.conftest import MockXeniaApi

TRACKER = "event.xenia_espresso_machine_shot_tracker"
# MA_STATUS values from the API documentation
ON = 1
BREWING = 3
DRAINING = 4
ISO_MILLISECONDS = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}\+00:00$")


def _shot(hass: HomeAssistant) -> dict | None:
    """Return the payload of the last shot_completed event, if any."""
    state = hass.states.get(TRACKER)
    assert state is not None
    if state.attributes.get("event_type") != "shot_completed":
        return None
    return dict(state.attributes)


async def brew(poll, seconds: int, **fields) -> None:
    """Brew for `seconds`, the cup weight rising by 1.5 g per second."""
    await poll(MA_STATUS=BREWING, SCALE_WEIGHT=0.0, **fields)
    for second in range(1, seconds + 1):
        await poll(MA_STATUS=BREWING, SCALE_WEIGHT=1.5 * second, **fields)


async def end_brew(poll, weight: float) -> None:
    """Stop brewing and let the afterflow pass."""
    for _ in range(3):
        await poll(MA_STATUS=ON, SCALE_WEIGHT=weight)


async def test_event_entities_snapshot(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
) -> None:
    """The shot tracker registry entry matches the snapshot."""
    registry_entry = entity_registry.async_get(TRACKER)
    assert registry_entry == snapshot(name=f"{TRACKER}-registry")


async def test_shot_is_fired_and_stored(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    poll,
) -> None:
    """A shot fires shot_completed with its curves after the afterflow and is stored."""
    await brew(poll, 25)
    assert hass.states.get(TRACKER).attributes["is_brewing"] is True

    await end_brew(poll, weight=38.0)

    shot = _shot(hass)
    assert shot is not None
    assert shot["is_brewing"] is False
    assert shot["duration_seconds"] == 26.0
    assert shot["afterflow_seconds"] == 2
    assert shot["timestamps"] == [float(second) for second in range(1, 29)]
    assert shot["weights"][:3] == [1.5, 3.0, 4.5]
    assert shot["weights"][-3:] == [38.0, 38.0, 38.0]
    assert shot["brew_end_time"] > shot["start_time"]
    assert ISO_MILLISECONDS.match(shot["start_time"])
    assert ISO_MILLISECONDS.match(shot["brew_end_time"])
    for curve in ("brew_group_temps", "brew_boiler_temps", "pump_pressures"):
        assert len(shot[curve]) == 28

    assert await listed_shots(hass, hass_ws_client) == [
        {
            "shot_id": shot["start_time"],
            "start_time": shot["start_time"],
            "brew_end_time": shot["brew_end_time"],
            "duration_seconds": 26.0,
            "final_weight_g": 38.0,
        }
    ]
    answer = await ws_command(
        hass,
        hass_ws_client,
        {"type": "xenia_home/shots/get", "shot_ids": [shot["start_time"]]},
    )
    [stored] = answer["result"]["shots"]
    assert stored["weights"] == shot["weights"]


@pytest.mark.parametrize(("seconds", "tracked"), [(8, False), (9, True)])
async def test_shots_last_ten_seconds_or_more(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    poll,
    seconds: int,
    tracked: bool,
) -> None:
    """A brew of ten seconds is a shot; a shorter one, like a flush, is not."""
    await brew(poll, seconds)
    await end_brew(poll, weight=15.0)
    shots = await listed_shots(hass, hass_ws_client)
    assert [s["duration_seconds"] for s in shots] == ([10.0] if tracked else [])
    assert (_shot(hass) is not None) is tracked


async def test_draining_counts_as_afterflow(hass: HomeAssistant, poll) -> None:
    """The machine drains after the brew; the shot ends when brewing stops."""
    await brew(poll, 12)
    await poll(MA_STATUS=DRAINING, SCALE_WEIGHT=19.0)
    await poll(MA_STATUS=DRAINING, SCALE_WEIGHT=19.5)
    await poll(MA_STATUS=ON, SCALE_WEIGHT=19.5)

    shot = _shot(hass)
    assert shot is not None
    assert shot["duration_seconds"] == 13.0
    assert shot["weights"][-3:] == [19.0, 19.5, 19.5]


async def test_final_weight_is_the_last_weight(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    poll,
) -> None:
    """The final weight is the cup weight at the end, not the highest one."""
    await brew(poll, 12)
    await end_brew(poll, weight=17.0)
    [summary] = await listed_shots(hass, hass_ws_client)
    assert summary["final_weight_g"] == 17.0


async def test_brew_during_afterflow_completes_the_shot_and_starts_a_new_one(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    poll,
) -> None:
    """Brewing again within the afterflow keeps the first shot and starts a new one."""
    await brew(poll, 15)
    await poll(MA_STATUS=ON, SCALE_WEIGHT=22.5)
    await brew(poll, 12)
    await end_brew(poll, weight=18.0)

    shot = _shot(hass)
    assert shot is not None
    assert shot["duration_seconds"] == 13.0
    assert shot["weights"][0] == 1.5
    stored = await listed_shots(hass, hass_ws_client)
    assert [s["duration_seconds"] for s in stored] == [13.0, 16.0]


async def test_slow_overview_single_costs_no_sample(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
) -> None:
    """A slow overview_single answer costs no shot sample and shifts none by a second."""
    # freezer comes before init_integration, so setup already runs on frozen time.
    mock_xenia_api.answer_slowly(freezer, "overview", 0.02)
    mock_xenia_api.answer_slowly(freezer, "overview_single", 0.4)
    mock_xenia_api.set_overview(MA_STATUS=BREWING, SCALE_WEIGHT=18.0)
    await run_for(hass, freezer, 25)
    mock_xenia_api.set_overview(MA_STATUS=ON, SCALE_WEIGHT=18.0)
    await run_for(hass, freezer, 4)

    shot = _shot(hass)
    assert shot is not None
    timestamps = shot["timestamps"]
    assert len(timestamps) >= 26
    assert timestamps == pytest.approx(
        [float(s) for s in range(1, len(timestamps) + 1)], abs=0.45
    )


async def test_failed_poll_adds_no_sample(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    poll,
) -> None:
    """A poll the machine does not answer is not recorded as a sample."""
    await brew(poll, 12)
    mock_xenia_api.override("get", "overview", exc=TimeoutError())
    await poll()
    mock_xenia_api.restore("get", "overview")
    await poll(MA_STATUS=BREWING, SCALE_WEIGHT=19.5)
    await end_brew(poll, weight=20.0)

    shot = _shot(hass)
    assert shot is not None
    assert 13.0 not in shot["timestamps"]
    assert shot["timestamps"][11:13] == [12.0, 14.0]
    assert len(shot["weights"]) == len(shot["timestamps"])


async def test_outage_at_brew_end_is_not_part_of_the_shot(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    poll,
) -> None:
    """A brew that ends while the machine does not answer ends at its last brewing poll."""
    await brew(poll, 12)
    mock_xenia_api.override("get", "overview", exc=TimeoutError())
    for _ in range(5):
        await poll()
    mock_xenia_api.restore("get", "overview")
    await end_brew(poll, weight=20.0)

    shot = _shot(hass)
    assert shot is not None
    assert shot["duration_seconds"] == 12.0
    assert shot["timestamps"][-1] == 12.0


async def test_machine_answering_within_the_afterflow_adds_a_sample(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    poll,
) -> None:
    """After a short outage at brew end, a poll within the afterflow is still recorded."""
    await brew(poll, 12)
    mock_xenia_api.override("get", "overview", exc=TimeoutError())
    await poll()
    mock_xenia_api.restore("get", "overview")
    await end_brew(poll, weight=20.0)

    shot = _shot(hass)
    assert shot is not None
    assert shot["duration_seconds"] == 12.0
    assert shot["timestamps"][-1] == 14.0


async def test_outage_while_brewing_is_part_of_the_shot(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    poll,
) -> None:
    """A brew that goes on after an outage ends when brewing stops, as usual."""
    await brew(poll, 6)
    mock_xenia_api.override("get", "overview", exc=TimeoutError())
    for _ in range(3):
        await poll()
    mock_xenia_api.restore("get", "overview")
    for second in range(10, 16):
        await poll(MA_STATUS=BREWING, SCALE_WEIGHT=1.5 * second)
    await end_brew(poll, weight=24.0)

    shot = _shot(hass)
    assert shot is not None
    assert shot["duration_seconds"] == 16.0


async def test_brew_after_a_long_outage_is_a_new_shot(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    mock_xenia_api: MockXeniaApi,
    poll,
) -> None:
    """Brewing seen more than 60 s after the shot start, past an outage, is a new brew.

    The machine stops the pump after at most 60 s.
    """
    await brew(poll, 12)
    mock_xenia_api.override("get", "overview", exc=TimeoutError())
    for _ in range(61):
        await poll()
    mock_xenia_api.restore("get", "overview")
    await brew(poll, 15)
    await end_brew(poll, weight=24.0)

    shot = _shot(hass)
    assert shot is not None
    assert shot["timestamps"][0] == 1.0
    assert shot["weights"][0] == 1.5
    stored = await listed_shots(hass, hass_ws_client)
    assert [s["duration_seconds"] for s in stored] == [16.0, 12.0]


async def test_long_brew_without_outage_stays_one_shot(
    hass: HomeAssistant, init_integration: MockConfigEntry, poll
) -> None:
    """A brew longer than 60 s, as extreme machine settings allow, is not split."""
    await brew(poll, 65)
    await end_brew(poll, weight=98.0)

    shot = _shot(hass)
    assert shot is not None
    assert shot["duration_seconds"] == 66.0


async def test_sample_with_a_missing_value_is_skipped(
    hass: HomeAssistant, init_integration: MockConfigEntry, poll
) -> None:
    """A poll that lacks a curve value adds no sample, so the curves stay aligned."""
    await brew(poll, 12)
    await poll(MA_STATUS=BREWING, SCALE_WEIGHT=19.5, PU_SENS_PRESS=None)
    await end_brew(poll, weight=20.0)

    shot = _shot(hass)
    assert shot is not None
    assert 13.0 not in shot["timestamps"]
    for curve in ("brew_group_temps", "pump_pressures", "weights", "flow_rates"):
        assert len(shot[curve]) == len(shot["timestamps"])


async def test_missing_weight_keeps_the_last_weight(
    hass: HomeAssistant, init_integration: MockConfigEntry, poll
) -> None:
    """A poll without a weight repeats the last one instead of looking like a tare."""
    await brew(poll, 12)
    await poll(MA_STATUS=BREWING, SCALE_WEIGHT=None)
    await poll(MA_STATUS=BREWING, SCALE_WEIGHT=19.5)
    await end_brew(poll, weight=20.0)

    shot = _shot(hass)
    assert shot is not None
    assert shot["weights"][0] == 1.5
    assert shot["weights"][11:14] == [18.0, 18.0, 19.5]


async def test_shot_without_a_complete_sample_is_dropped(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    poll,
) -> None:
    """A shot in which every poll lacks a curve value is not stored."""
    for _ in range(14):
        await poll(MA_STATUS=BREWING, PU_SENS_PRESS=None)
    for _ in range(3):
        await poll(MA_STATUS=ON, PU_SENS_PRESS=None)

    assert _shot(hass) is None
    assert await listed_shots(hass, hass_ws_client) == []


async def test_shot_without_scale_weight_is_stored(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    poll,
) -> None:
    """A machine that reports no scale weight still records its shots, at 0 g."""
    for _ in range(14):
        await poll(MA_STATUS=BREWING, SCALE_WEIGHT=None)
    for _ in range(3):
        await poll(MA_STATUS=ON, SCALE_WEIGHT=None)

    shot = _shot(hass)
    assert shot is not None
    assert set(shot["weights"]) == {0.0}
    assert len(await listed_shots(hass, hass_ws_client)) == 1


async def test_overdue_afterflow_adds_no_sample(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    poll,
) -> None:
    """A poll answered only after the afterflow ends the shot without a sample."""
    await brew(poll, 12)
    await poll(MA_STATUS=ON, SCALE_WEIGHT=20.0)
    mock_xenia_api.override("get", "overview", exc=TimeoutError())
    await poll()
    await poll()
    mock_xenia_api.restore("get", "overview")
    await poll(MA_STATUS=ON, SCALE_WEIGHT=20.5)

    shot = _shot(hass)
    assert shot is not None
    assert shot["weights"][-1] == 20.0


@pytest.mark.parametrize(
    ("old_firmware", "fields", "flow"),
    [
        (False, {"PU_SENS_SCALE_RATE": 1.35}, 1.35),
        (False, {"PU_SENS_SCALE_RATE": ""}, 0.0),
        (True, {}, 12.3),
    ],
)
async def test_flow_comes_from_scale_rate_or_flow_meter(
    hass: HomeAssistant,
    mock_xenia_api: MockXeniaApi,
    poll,
    old_firmware: bool,
    fields: dict,
    flow: float,
) -> None:
    """The scale rate is the flow; without a usable one the flow meter is."""
    if old_firmware:
        mock_xenia_api.use_old_firmware()
    await brew(poll, 12, **fields)
    await end_brew(poll, weight=18.0)
    shot = _shot(hass)
    assert shot is not None
    assert shot["flow_rates"][:12] == [flow] * 12


async def test_tare_at_brew_start_zeroes_earlier_weights(
    hass: HomeAssistant, poll
) -> None:
    """The auto tare after the brew starts resets the cup weight recorded so far."""
    await poll(MA_STATUS=BREWING, SCALE_WEIGHT=238.6)
    await poll(MA_STATUS=BREWING, SCALE_WEIGHT=238.6)
    await poll(MA_STATUS=BREWING, SCALE_WEIGHT=238.6)
    for second in range(1, 11):
        await poll(MA_STATUS=BREWING, SCALE_WEIGHT=2.0 * second)
    await end_brew(poll, weight=20.0)

    shot = _shot(hass)
    assert shot is not None
    assert shot["weights"][:3] == [0.0, 0.0, 2.0]


@pytest.mark.parametrize("tared", [0.1, 28.0])
async def test_tare_in_afterflow_ends_the_shot(
    hass: HomeAssistant, poll, tared: float
) -> None:
    """A drop of more than 2 g after the brew is the tare; it ends the shot at once."""
    await brew(poll, 20)
    await poll(MA_STATUS=ON, SCALE_WEIGHT=30.5)
    await poll(MA_STATUS=ON, SCALE_WEIGHT=tared)

    shot = _shot(hass)
    assert shot is not None
    assert shot["weights"][-1] == 30.5


@pytest.mark.parametrize("weight", [30.0, 28.5])
async def test_small_drop_in_afterflow_is_recorded(
    hass: HomeAssistant, poll, weight: float
) -> None:
    """A drop of up to 2 g is a real sample, not a tare."""
    await brew(poll, 20)
    await poll(MA_STATUS=ON, SCALE_WEIGHT=30.5)
    await poll(MA_STATUS=ON, SCALE_WEIGHT=weight)
    assert _shot(hass) is None

    await poll(MA_STATUS=ON, SCALE_WEIGHT=weight)
    shot = _shot(hass)
    assert shot is not None
    assert shot["weights"][-3:] == [30.5, weight, weight]
