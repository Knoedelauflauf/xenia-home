"""Tests for event.py — XeniaShotTracker and ShotData."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from custom_components.xenia_home.coordinator import (
    XeniaCoordinatorData,
)
from custom_components.xenia_home.event import ShotData, XeniaShotTracker
from custom_components.xenia_home.xenia import (
    MachineStatus,
    XeniaOverviewData,
    XeniaOverviewSingleData,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_coordinator(ma_status: MachineStatus = MachineStatus.ON) -> MagicMock:
    coord = MagicMock()
    coord.config_entry = MagicMock()
    coord.config_entry.data = {"host": "xenia.local"}

    overview = XeniaOverviewData.from_dict(
        {
            "MA_STATUS": ma_status.value,
            "BG_SENS_TEMP_A": 93.0,
            "BB_SENS_TEMP_A": 130.0,
            "PU_SENS_PRESS": 9.0,
            "PU_SENS_FLOW_METER_ML": 5.0,
            "SCALE_WEIGHT": 18.0,
        }
    )
    overview_single = XeniaOverviewSingleData.from_dict({})
    coord.data = XeniaCoordinatorData(
        overview=overview, overview_single=overview_single
    )
    return coord


def _make_tracker(coordinator: MagicMock) -> XeniaShotTracker:
    with patch(
        "custom_components.xenia_home.entity.XeniaEntity.__init__", return_value=None
    ):
        tracker = XeniaShotTracker.__new__(XeniaShotTracker)
        tracker.coordinator = coordinator
        tracker.hass = MagicMock()
        XeniaShotTracker.__init__(tracker, coordinator)
    return tracker


def _update_status(tracker: XeniaShotTracker, status: MachineStatus) -> None:
    """Update the coordinator's machine status and trigger a coordinator update."""
    tracker.coordinator.data.overview._replace  # just to ensure it's a real object
    # Patch the status directly on the dataclass
    tracker.coordinator.data = XeniaCoordinatorData(
        overview=XeniaOverviewData.from_dict(
            {
                "MA_STATUS": status.value,
                "BG_SENS_TEMP_A": 93.0,
                "BB_SENS_TEMP_A": 130.0,
                "PU_SENS_PRESS": 9.0,
                "PU_SENS_FLOW_METER_ML": 5.0,
                "SCALE_WEIGHT": 18.5,
            }
        ),
        overview_single=XeniaOverviewSingleData.from_dict({}),
    )
    tracker.async_write_ha_state = MagicMock()
    tracker._handle_coordinator_update()


# ===========================================================================
# ShotData
# ===========================================================================


def test_shot_data_to_dict_returns_all_fields() -> None:
    shot = ShotData(
        start_time="2026-01-01T10:00:00",
        brew_end_time="2026-01-01T10:00:30",
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
    assert d["start_time"] == "2026-01-01T10:00:00"
    assert d["duration_seconds"] == 30.0
    assert d["timestamps"] == [0.0, 1.0]
    assert d["brew_end_time"] == "2026-01-01T10:00:30"


def test_shot_data_to_dict_brew_end_time_can_be_none() -> None:
    shot = ShotData(
        start_time="2026-01-01T10:00:00",
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
    d = shot.to_dict()
    assert d["brew_end_time"] is None


# ===========================================================================
# XeniaShotTracker — initialization
# ===========================================================================


def test_shot_tracker_unique_id_contains_host() -> None:
    coord = _make_coordinator()
    tracker = _make_tracker(coord)
    assert "xenia.local" in tracker._attr_unique_id


def test_shot_tracker_translation_key_is_set() -> None:
    coord = _make_coordinator()
    tracker = _make_tracker(coord)
    assert tracker._attr_translation_key == "shot_tracker"


def test_shot_tracker_event_types_contains_shot_completed() -> None:
    coord = _make_coordinator()
    tracker = _make_tracker(coord)
    assert "shot_completed" in tracker._attr_event_types


def test_shot_tracker_initial_state_not_brewing() -> None:
    coord = _make_coordinator()
    tracker = _make_tracker(coord)
    assert tracker._is_brewing is False


def test_shot_tracker_initial_shot_start_time_is_none() -> None:
    coord = _make_coordinator()
    tracker = _make_tracker(coord)
    assert tracker._shot_start_time is None


def test_shot_tracker_extra_state_attributes_returns_is_brewing() -> None:
    coord = _make_coordinator()
    tracker = _make_tracker(coord)
    attrs = tracker.extra_state_attributes
    assert "is_brewing" in attrs
    assert attrs["is_brewing"] is False


# ===========================================================================
# _start_shot_tracking
# ===========================================================================


def test_start_shot_tracking_sets_shot_start_time() -> None:
    coord = _make_coordinator()
    tracker = _make_tracker(coord)
    tracker._start_shot_tracking()
    assert tracker._shot_start_time is not None


def test_start_shot_tracking_clears_all_lists() -> None:
    coord = _make_coordinator()
    tracker = _make_tracker(coord)
    tracker._brew_group_temps = [1.0, 2.0]
    tracker._timestamps = [0.5, 1.5]
    tracker._start_shot_tracking()
    assert tracker._brew_group_temps == []
    assert tracker._timestamps == []


def test_start_shot_tracking_clears_brew_end_time() -> None:
    coord = _make_coordinator()
    tracker = _make_tracker(coord)
    tracker._brew_end_time = datetime.now()
    tracker._start_shot_tracking()
    assert tracker._brew_end_time is None


# ===========================================================================
# _start_afterflow
# ===========================================================================


def test_start_afterflow_sets_afterflow_until() -> None:
    coord = _make_coordinator()
    tracker = _make_tracker(coord)
    tracker._start_afterflow()
    assert tracker._afterflow_until is not None


def test_start_afterflow_does_not_reset_if_already_active() -> None:
    coord = _make_coordinator()
    tracker = _make_tracker(coord)
    first_time = datetime.now() + timedelta(seconds=10)
    tracker._afterflow_until = first_time
    tracker._start_afterflow()
    # Should not overwrite
    assert tracker._afterflow_until == first_time


def test_start_afterflow_sets_brew_end_time() -> None:
    coord = _make_coordinator()
    tracker = _make_tracker(coord)
    tracker._start_afterflow()
    assert tracker._brew_end_time is not None


def test_start_afterflow_resets_sample_counter() -> None:
    coord = _make_coordinator()
    tracker = _make_tracker(coord)
    tracker._afterflow_samples = 5
    tracker._start_afterflow()
    assert tracker._afterflow_samples == 0


# ===========================================================================
# _cancel_afterflow
# ===========================================================================


def test_cancel_afterflow_clears_afterflow_until() -> None:
    coord = _make_coordinator()
    tracker = _make_tracker(coord)
    tracker._afterflow_until = datetime.now() + timedelta(seconds=5)
    tracker._cancel_afterflow()
    assert tracker._afterflow_until is None


def test_cancel_afterflow_resets_samples() -> None:
    coord = _make_coordinator()
    tracker = _make_tracker(coord)
    tracker._afterflow_samples = 3
    tracker._cancel_afterflow()
    assert tracker._afterflow_samples == 0


# ===========================================================================
# _collect_shot_data
# ===========================================================================


def test_collect_shot_data_does_nothing_if_shot_not_started() -> None:
    coord = _make_coordinator()
    tracker = _make_tracker(coord)
    tracker._shot_start_time = None
    tracker._collect_shot_data()
    assert tracker._brew_group_temps == []


def test_collect_shot_data_appends_sensor_values() -> None:
    coord = _make_coordinator(MachineStatus.BREWING)
    tracker = _make_tracker(coord)
    tracker._shot_start_time = datetime.now()
    tracker._is_brewing = True
    tracker._collect_shot_data()
    assert len(tracker._brew_group_temps) == 1
    assert len(tracker._pump_pressures) == 1
    assert len(tracker._weights) == 1
    assert len(tracker._timestamps) == 1


def test_collect_shot_data_increments_afterflow_samples_when_not_brewing() -> None:
    coord = _make_coordinator(MachineStatus.ON)
    tracker = _make_tracker(coord)
    tracker._shot_start_time = datetime.now()
    tracker._is_brewing = False
    tracker._afterflow_until = datetime.now() + timedelta(seconds=5)
    tracker._collect_shot_data()
    assert tracker._afterflow_samples == 1


# ===========================================================================
# _complete_shot_tracking
# ===========================================================================


def test_complete_shot_tracking_does_nothing_if_no_start_time() -> None:
    coord = _make_coordinator()
    tracker = _make_tracker(coord)
    tracker._shot_start_time = None
    tracker._timestamps = []
    # Should not raise
    tracker._complete_shot_tracking()


def test_complete_shot_tracking_does_nothing_if_no_timestamps() -> None:
    coord = _make_coordinator()
    tracker = _make_tracker(coord)
    tracker._shot_start_time = datetime.now()
    tracker._timestamps = []
    tracker._complete_shot_tracking()


def test_complete_shot_tracking_ignores_short_shots() -> None:
    coord = _make_coordinator()
    tracker = _make_tracker(coord)
    tracker._trigger_event = MagicMock()
    tracker._shot_start_time = datetime.now() - timedelta(seconds=5)
    tracker._timestamps = [0.0, 1.0]
    tracker._brew_group_temps = [93.0, 93.0]
    tracker._brew_boiler_temps = [130.0, 130.0]
    tracker._pump_pressures = [9.0, 9.0]
    tracker._flow_rates = [5.0, 5.0]
    tracker._weights = [0.0, 5.0]
    tracker._complete_shot_tracking()
    tracker._trigger_event.assert_not_called()


def test_complete_shot_tracking_fires_event_for_long_enough_shot() -> None:
    coord = _make_coordinator()
    tracker = _make_tracker(coord)
    tracker._trigger_event = MagicMock()
    tracker._shot_start_time = datetime.now() - timedelta(seconds=25)
    tracker._timestamps = [0.0, 5.0, 10.0, 15.0, 20.0]
    tracker._brew_group_temps = [93.0] * 5
    tracker._brew_boiler_temps = [130.0] * 5
    tracker._pump_pressures = [9.0] * 5
    tracker._flow_rates = [5.0] * 5
    tracker._weights = [0.0, 5.0, 10.0, 15.0, 18.0]
    tracker._complete_shot_tracking()
    tracker._trigger_event.assert_called_once()
    call_args = tracker._trigger_event.call_args
    assert call_args[0][0] == "shot_completed"


def test_complete_shot_tracking_uses_brew_end_time_for_duration_when_available() -> (
    None
):
    coord = _make_coordinator()
    tracker = _make_tracker(coord)
    tracker._trigger_event = MagicMock()
    start = datetime.now() - timedelta(seconds=30)
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
    shot_data_arg = tracker._trigger_event.call_args[0][1]
    assert shot_data_arg["duration_seconds"] == pytest.approx(25.0, abs=1.0)


def test_complete_shot_tracking_cancels_afterflow_when_done() -> None:
    coord = _make_coordinator()
    tracker = _make_tracker(coord)
    tracker._trigger_event = MagicMock()
    tracker._afterflow_until = datetime.now() + timedelta(seconds=5)
    tracker._shot_start_time = datetime.now() - timedelta(seconds=25)
    tracker._timestamps = list(range(25))
    tracker._brew_group_temps = [93.0] * 25
    tracker._brew_boiler_temps = [130.0] * 25
    tracker._pump_pressures = [9.0] * 25
    tracker._flow_rates = [5.0] * 25
    tracker._weights = [float(i) for i in range(25)]
    tracker._complete_shot_tracking()
    assert tracker._afterflow_until is None


# ===========================================================================
# _handle_coordinator_update — state machine transitions
# ===========================================================================


def test_handle_update_starts_tracking_when_brewing_begins() -> None:
    coord = _make_coordinator(MachineStatus.ON)
    tracker = _make_tracker(coord)
    tracker.async_write_ha_state = MagicMock()
    tracker._is_brewing = False

    # Simulate transition to BREWING
    coord.data = XeniaCoordinatorData(
        overview=XeniaOverviewData.from_dict(
            {"MA_STATUS": MachineStatus.BREWING.value}
        ),
        overview_single=XeniaOverviewSingleData.from_dict({}),
    )
    tracker._handle_coordinator_update()

    assert tracker._shot_start_time is not None
    assert tracker._is_brewing is True


def test_handle_update_collects_data_while_brewing() -> None:
    coord = _make_coordinator(MachineStatus.BREWING)
    tracker = _make_tracker(coord)
    tracker.async_write_ha_state = MagicMock()
    tracker._is_brewing = True
    tracker._shot_start_time = datetime.now()

    coord.data = XeniaCoordinatorData(
        overview=XeniaOverviewData.from_dict(
            {"MA_STATUS": MachineStatus.BREWING.value}
        ),
        overview_single=XeniaOverviewSingleData.from_dict({}),
    )
    tracker._handle_coordinator_update()

    assert len(tracker._timestamps) >= 1


def test_handle_update_starts_afterflow_when_brewing_stops() -> None:
    coord = _make_coordinator(MachineStatus.BREWING)
    tracker = _make_tracker(coord)
    tracker.async_write_ha_state = MagicMock()
    tracker._is_brewing = True
    tracker._shot_start_time = datetime.now()

    coord.data = XeniaCoordinatorData(
        overview=XeniaOverviewData.from_dict({"MA_STATUS": MachineStatus.ON.value}),
        overview_single=XeniaOverviewSingleData.from_dict({}),
    )
    tracker._handle_coordinator_update()

    assert tracker._afterflow_until is not None
    assert tracker._is_brewing is False


def test_handle_update_completes_shot_after_afterflow_expires() -> None:
    coord = _make_coordinator(MachineStatus.ON)
    tracker = _make_tracker(coord)
    tracker.async_write_ha_state = MagicMock()
    tracker._trigger_event = MagicMock()
    tracker._is_brewing = False
    tracker._shot_start_time = datetime.now() - timedelta(seconds=30)
    tracker._timestamps = list(range(20))
    tracker._brew_group_temps = [93.0] * 20
    tracker._brew_boiler_temps = [130.0] * 20
    tracker._pump_pressures = [9.0] * 20
    tracker._flow_rates = [5.0] * 20
    tracker._weights = [float(i) for i in range(20)]
    # Set afterflow to already expired
    tracker._afterflow_until = datetime.now() - timedelta(seconds=1)

    coord.data = XeniaCoordinatorData(
        overview=XeniaOverviewData.from_dict({"MA_STATUS": MachineStatus.ON.value}),
        overview_single=XeniaOverviewSingleData.from_dict({}),
    )
    tracker._handle_coordinator_update()

    tracker._trigger_event.assert_called_once()


def test_handle_update_cancels_afterflow_when_new_brew_starts() -> None:
    coord = _make_coordinator(MachineStatus.ON)
    tracker = _make_tracker(coord)
    tracker.async_write_ha_state = MagicMock()
    tracker._is_brewing = False
    tracker._afterflow_until = datetime.now() + timedelta(seconds=5)

    # Transition directly to brewing again
    coord.data = XeniaCoordinatorData(
        overview=XeniaOverviewData.from_dict(
            {"MA_STATUS": MachineStatus.BREWING.value}
        ),
        overview_single=XeniaOverviewSingleData.from_dict({}),
    )
    tracker._handle_coordinator_update()

    assert tracker._afterflow_until is None


def test_afterflow_ends_early_on_scale_auto_tare() -> None:
    """Scale sending 0g during afterflow should complete the shot immediately."""
    coord = _make_coordinator(MachineStatus.ON)
    tracker = _make_tracker(coord)
    tracker.async_write_ha_state = MagicMock()
    tracker._trigger_event = MagicMock()
    tracker._is_brewing = False
    tracker._shot_start_time = datetime.now() - timedelta(seconds=30)
    tracker._timestamps = list(range(20))
    tracker._brew_group_temps = [93.0] * 20
    tracker._brew_boiler_temps = [130.0] * 20
    tracker._pump_pressures = [9.0] * 20
    tracker._flow_rates = [5.0] * 20
    tracker._weights = [float(i) for i in range(20)]  # last value is 19.0
    tracker._afterflow_until = datetime.now() + timedelta(seconds=5)
    tracker._brew_end_time = datetime.now()

    # Scale reports 0g (auto-tare)
    coord.data = XeniaCoordinatorData(
        overview=XeniaOverviewData.from_dict(
            {"MA_STATUS": MachineStatus.ON.value, "SCALE_WEIGHT": 0.0}
        ),
        overview_single=XeniaOverviewSingleData.from_dict({}),
    )
    tracker._handle_coordinator_update()

    # Shot should be completed, 0g not in weights
    tracker._trigger_event.assert_called_once()
    assert tracker._weights[-1] == 19.0


def test_zero_weight_during_brewing_is_recorded() -> None:
    """0g during active brewing should be recorded normally."""
    coord = _make_coordinator(MachineStatus.BREWING)
    tracker = _make_tracker(coord)
    tracker.async_write_ha_state = MagicMock()
    tracker._is_brewing = True
    tracker._shot_start_time = datetime.now() - timedelta(seconds=5)
    tracker._timestamps = [0.0, 1.0]
    tracker._brew_group_temps = [93.0, 93.0]
    tracker._brew_boiler_temps = [130.0, 130.0]
    tracker._pump_pressures = [9.0, 9.0]
    tracker._flow_rates = [5.0, 5.0]
    tracker._weights = [10.0, 15.0]

    # Scale reports 0g while still brewing
    coord.data = XeniaCoordinatorData(
        overview=XeniaOverviewData.from_dict(
            {"MA_STATUS": MachineStatus.BREWING.value, "SCALE_WEIGHT": 0.0}
        ),
        overview_single=XeniaOverviewSingleData.from_dict({}),
    )
    tracker._handle_coordinator_update()

    # 0g should be recorded
    assert tracker._weights[-1] == 0.0
    assert len(tracker._weights) == 3


def test_handle_update_writes_ha_state_every_call() -> None:
    coord = _make_coordinator(MachineStatus.ON)
    tracker = _make_tracker(coord)
    tracker.async_write_ha_state = MagicMock()
    tracker._handle_coordinator_update()
    tracker.async_write_ha_state.assert_called_once()
