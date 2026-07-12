"""Tests for event.py — XeniaShotTracker and ShotData."""

from datetime import timedelta

from homeassistant.helpers.entity_component import DATA_INSTANCES
from homeassistant.util import dt as dt_util
import pytest

from custom_components.xenia_home.coordinator import XeniaCoordinatorData
from custom_components.xenia_home.event import ShotData
from custom_components.xenia_home.xenia import MachineStatus, XeniaOverviewData
from tests.fixtures.api_responses import OVERVIEW_PAYLOAD

TRACKER = "event.xenia_espresso_machine_shot_tracker"


async def test_event_entities_snapshot(
    hass, init_integration, snapshot, entity_registry
):
    entity_ids = sorted(
        e.entity_id
        for e in entity_registry.entities.values()
        if e.platform == "xenia_home" and e.domain == "event"
    )
    assert entity_ids
    for entity_id in entity_ids:
        registry_entry = entity_registry.async_get(entity_id)
        # State of an event entity is volatile (last event timestamp).
        # Snapshot the registry entry only.
        assert registry_entry == snapshot(name=f"{entity_id}-registry")


# ===========================================================================
# ShotData
# ===========================================================================


def test_shot_data_to_dict_has_all_fields() -> None:
    shot = ShotData(
        start_time="2026-01-01T10:00:00.000+00:00",
        brew_end_time="2026-01-01T10:00:30.000+00:00",
        afterflow_seconds=2,
        duration_seconds=30.0,
        timestamps=[0.0, 1.0],
        brew_group_temps=[93.0, 93.5],
        brew_boiler_temps=[130.0, 130.0],
        pump_pressures=[9.0, 9.1],
        flow_rates=[5.0, 5.5],
        weights=[0.0, 10.0],
    )
    d = shot.to_dict()
    assert d["start_time"] == "2026-01-01T10:00:00.000+00:00"
    assert d["duration_seconds"] == 30.0
    assert d["timestamps"] == [0.0, 1.0]
    assert d["brew_end_time"] == "2026-01-01T10:00:30.000+00:00"


def test_shot_data_brew_end_time_optional() -> None:
    shot = ShotData(
        start_time="2026-01-01T10:00:00.000+00:00",
        brew_end_time=None,
        afterflow_seconds=2,
        duration_seconds=25.0,
        timestamps=[],
        brew_group_temps=[],
        brew_boiler_temps=[],
        pump_pressures=[],
        flow_rates=[],
        weights=[],
    )
    assert shot.to_dict()["brew_end_time"] is None


# ===========================================================================
# Helpers to grab the live entity object and prime the state machine
# ===========================================================================


def _get_tracker(hass, init_integration):
    """Return the XeniaShotTracker entity instance from runtime data."""
    component = hass.data[DATA_INSTANCES].get("event")
    if component is not None:
        for entity in component.entities:
            if entity.entity_id == TRACKER:
                return entity
    raise AssertionError(f"tracker entity {TRACKER} not found")


async def _drive_overview(hass, mock_xenia_api, init_integration, **fields):
    """Push overview field overrides through the coordinator."""
    coordinator = init_integration.runtime_data.coordinator
    new_overview = XeniaOverviewData.from_dict({**mock_xenia_api._overview, **fields})
    new_data = XeniaCoordinatorData(
        overview=new_overview,
        overview_single=coordinator.data.overview_single,
    )
    coordinator.async_set_updated_data(new_data)
    await hass.async_block_till_done()


async def _drive_status(hass, mock_xenia_api, init_integration, status: MachineStatus):
    """Push a new MA_STATUS through the coordinator and let listeners run."""
    await _drive_overview(hass, mock_xenia_api, init_integration, MA_STATUS=int(status))


# ===========================================================================
# State-machine transitions driven through the real coordinator
# ===========================================================================


async def test_tracker_starts_shot_when_brewing_begins(
    hass, init_integration, mock_xenia_api
):
    tracker = _get_tracker(hass, init_integration)
    assert tracker._is_brewing is False
    await _drive_status(hass, mock_xenia_api, init_integration, MachineStatus.BREWING)
    assert tracker._is_brewing is True
    assert tracker._shot_start_time is not None


async def test_tracker_starts_afterflow_when_brewing_stops(
    hass, init_integration, mock_xenia_api
):
    tracker = _get_tracker(hass, init_integration)
    await _drive_status(hass, mock_xenia_api, init_integration, MachineStatus.BREWING)
    assert tracker._is_brewing is True
    await _drive_status(hass, mock_xenia_api, init_integration, MachineStatus.ON)
    assert tracker._is_brewing is False
    assert tracker._afterflow_until is not None


async def test_tracker_cancels_afterflow_on_new_brew(
    hass, init_integration, mock_xenia_api
):
    tracker = _get_tracker(hass, init_integration)
    await _drive_status(hass, mock_xenia_api, init_integration, MachineStatus.BREWING)
    await _drive_status(hass, mock_xenia_api, init_integration, MachineStatus.ON)
    assert tracker._afterflow_until is not None
    await _drive_status(hass, mock_xenia_api, init_integration, MachineStatus.BREWING)
    assert tracker._afterflow_until is None


# ===========================================================================
# Direct entity-instance tests for the internal helpers
# ===========================================================================


async def test_start_shot_tracking_clears_lists(hass, init_integration):
    tracker = _get_tracker(hass, init_integration)
    tracker._brew_group_temps = [1.0, 2.0]
    tracker._timestamps = [0.5, 1.5]
    tracker._brew_end_time = dt_util.utcnow()
    tracker._start_shot_tracking()
    assert tracker._brew_group_temps == []
    assert tracker._timestamps == []
    assert tracker._brew_end_time is None
    assert tracker._shot_start_time is not None


async def test_start_afterflow_does_not_reset_if_already_active(hass, init_integration):
    tracker = _get_tracker(hass, init_integration)
    first = dt_util.utcnow() + timedelta(seconds=10)
    tracker._afterflow_until = first
    tracker._start_afterflow()
    assert tracker._afterflow_until == first


async def test_cancel_afterflow_clears_state(hass, init_integration):
    tracker = _get_tracker(hass, init_integration)
    tracker._afterflow_until = dt_util.utcnow() + timedelta(seconds=5)
    tracker._afterflow_samples = 3
    tracker._cancel_afterflow()
    assert tracker._afterflow_until is None
    assert tracker._afterflow_samples == 0


async def test_complete_shot_ignores_short_shots(hass, init_integration):
    tracker = _get_tracker(hass, init_integration)
    fired: list = []
    tracker._trigger_event = lambda name, data: fired.append((name, data))
    tracker._shot_start_time = dt_util.utcnow() - timedelta(seconds=5)
    tracker._timestamps = [0.0, 1.0]
    tracker._brew_group_temps = [93.0, 93.0]
    tracker._brew_boiler_temps = [130.0, 130.0]
    tracker._pump_pressures = [9.0, 9.0]
    tracker._flow_rates = [5.0, 5.0]
    tracker._weights = [0.0, 5.0]
    tracker._complete_shot_tracking()
    assert fired == []


async def test_complete_shot_fires_for_long_enough_shot(hass, init_integration):
    tracker = _get_tracker(hass, init_integration)
    fired: list = []
    tracker._trigger_event = lambda name, data: fired.append((name, data))
    tracker._shot_start_time = dt_util.utcnow() - timedelta(seconds=25)
    tracker._timestamps = [0.0, 5.0, 10.0, 15.0, 20.0]
    tracker._brew_group_temps = [93.0] * 5
    tracker._brew_boiler_temps = [130.0] * 5
    tracker._pump_pressures = [9.0] * 5
    tracker._flow_rates = [5.0] * 5
    tracker._weights = [0.0, 5.0, 10.0, 15.0, 18.0]
    tracker._complete_shot_tracking()
    assert len(fired) == 1
    name, data = fired[0]
    assert name == "shot_completed"
    assert "duration_seconds" in data


async def test_complete_shot_uses_brew_end_time_for_duration(hass, init_integration):
    tracker = _get_tracker(hass, init_integration)
    fired: list = []
    tracker._trigger_event = lambda name, data: fired.append((name, data))
    start = dt_util.utcnow() - timedelta(seconds=30)
    brew_end = start + timedelta(seconds=25)
    tracker._shot_start_time = start
    tracker._brew_end_time = brew_end
    tracker._timestamps = list(range(25))
    tracker._brew_group_temps = [93.0] * 25
    tracker._brew_boiler_temps = [130.0] * 25
    tracker._pump_pressures = [9.0] * 25
    tracker._flow_rates = [5.0] * 25
    tracker._weights = [float(i) for i in range(25)]
    tracker._complete_shot_tracking()
    assert pytest.approx(fired[0][1]["duration_seconds"], abs=1.0) == 25.0


async def test_complete_shot_cancels_afterflow(hass, init_integration):
    tracker = _get_tracker(hass, init_integration)
    tracker._trigger_event = lambda *a, **k: None
    tracker._afterflow_until = dt_util.utcnow() + timedelta(seconds=5)
    tracker._shot_start_time = dt_util.utcnow() - timedelta(seconds=25)
    tracker._timestamps = list(range(25))
    tracker._brew_group_temps = [93.0] * 25
    tracker._brew_boiler_temps = [130.0] * 25
    tracker._pump_pressures = [9.0] * 25
    tracker._flow_rates = [5.0] * 25
    tracker._weights = [float(i) for i in range(25)]
    tracker._complete_shot_tracking()
    assert tracker._afterflow_until is None


async def test_collect_uses_scale_rate_when_present(
    hass, init_integration, mock_xenia_api
):
    tracker = _get_tracker(hass, init_integration)
    fields = {
        "MA_STATUS": int(MachineStatus.BREWING),
        "PU_SENS_SCALE_RATE": 1.27,
        "PU_SENS_FLOW_METER_ML": 99.0,
    }
    for _ in range(2):
        await _drive_overview(hass, mock_xenia_api, init_integration, **fields)
    assert tracker._flow_rates == [1.27]


async def test_collect_falls_back_to_ml_key_on_old_firmware(
    hass, init_integration, mock_xenia_api
):
    tracker = _get_tracker(hass, init_integration)
    await _drive_status(hass, mock_xenia_api, init_integration, MachineStatus.BREWING)
    await _drive_status(hass, mock_xenia_api, init_integration, MachineStatus.BREWING)
    assert tracker._flow_rates == [OVERVIEW_PAYLOAD["PU_SENS_FLOW_METER_ML"]]


async def test_collect_scale_rate_hiccup_falls_back_to_ml_for_sample(
    hass, init_integration, mock_xenia_api
):
    tracker = _get_tracker(hass, init_integration)
    fields = {"MA_STATUS": int(MachineStatus.BREWING), "PU_SENS_SCALE_RATE": 1.27}
    await _drive_overview(hass, mock_xenia_api, init_integration, **fields)
    await _drive_overview(hass, mock_xenia_api, init_integration, **fields)
    await _drive_overview(
        hass,
        mock_xenia_api,
        init_integration,
        MA_STATUS=int(MachineStatus.BREWING),
        PU_SENS_SCALE_RATE="",
    )
    assert tracker._flow_rates == [1.27, OVERVIEW_PAYLOAD["PU_SENS_FLOW_METER_ML"]]
