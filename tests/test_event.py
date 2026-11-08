"""Tests for the shot tracker event entity."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from syrupy.assertion import SnapshotAssertion

from custom_components.xenia_home.xenia import MachineStatus

from tests.fixtures.api_responses import OVERVIEW_PAYLOAD

TRACKER = "event.xenia_espresso_machine_shot_tracker"
BREWING = int(MachineStatus.BREWING)
ON = int(MachineStatus.ON)
FLOW_METER = OVERVIEW_PAYLOAD["PU_SENS_FLOW_METER_ML"]


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
    hass: HomeAssistant, init_integration: MockConfigEntry, poll
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
    for curve in ("brew_group_temps", "brew_boiler_temps", "pump_pressures"):
        assert len(shot[curve]) == 28

    store = init_integration.runtime_data.shot_store
    assert [s["start_time"] for s in store.list_shots()] == [shot["start_time"]]
    stored = (await store.async_get_shots([shot["start_time"]]))[0]
    assert stored["weights"] == shot["weights"]


async def test_short_shot_is_ignored(
    hass: HomeAssistant, init_integration: MockConfigEntry, poll
) -> None:
    """A brew shorter than ten seconds is not a shot."""
    await brew(poll, 5)
    await end_brew(poll, weight=7.5)
    assert _shot(hass) is None
    assert init_integration.runtime_data.shot_store.list_shots() == []


async def test_brew_during_afterflow_starts_a_new_shot(
    hass: HomeAssistant, poll
) -> None:
    """Brewing again within the afterflow starts a new shot with empty curves."""
    await brew(poll, 15)
    await poll(MA_STATUS=ON, SCALE_WEIGHT=22.5)
    await brew(poll, 12)
    await end_brew(poll, weight=18.0)

    shot = _shot(hass)
    assert shot is not None
    assert shot["duration_seconds"] == 13.0
    assert shot["weights"][0] == 1.5


@pytest.mark.parametrize(
    ("fields", "flow"),
    [
        ({"PU_SENS_SCALE_RATE": 1.27, "PU_SENS_FLOW_METER_ML": 99.0}, 1.27),
        ({}, FLOW_METER),
        ({"PU_SENS_SCALE_RATE": ""}, FLOW_METER),
    ],
)
async def test_flow_comes_from_scale_rate_or_flow_meter(
    hass: HomeAssistant, poll, fields: dict, flow: float
) -> None:
    """The scale rate is the flow; without a usable one the flow meter is."""
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


async def test_tare_in_afterflow_ends_the_shot(hass: HomeAssistant, poll) -> None:
    """The auto tare after the brew ends the shot at once, without the tared sample."""
    await brew(poll, 20)
    await poll(MA_STATUS=ON, SCALE_WEIGHT=30.5)
    await poll(MA_STATUS=ON, SCALE_WEIGHT=0.1)

    shot = _shot(hass)
    assert shot is not None
    assert shot["weights"][-1] == 30.5


async def test_small_drop_in_afterflow_is_recorded(hass: HomeAssistant, poll) -> None:
    """A drop below the tare threshold is a real sample, not a tare."""
    await brew(poll, 20)
    await poll(MA_STATUS=ON, SCALE_WEIGHT=30.5)
    await poll(MA_STATUS=ON, SCALE_WEIGHT=30.0)
    assert _shot(hass) is None

    await poll(MA_STATUS=ON, SCALE_WEIGHT=30.0)
    shot = _shot(hass)
    assert shot is not None
    assert shot["weights"][-3:] == [30.5, 30.0, 30.0]
