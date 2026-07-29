"""The recorder must not persist the shot curve arrays."""

from datetime import timedelta
from functools import partial

from homeassistant.components.recorder import get_instance, history
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.xenia_home.xenia import MachineStatus
from tests.test_event import TRACKER, _drive_status, _get_tracker

CURVE_ATTRS = (
    "timestamps",
    "brew_group_temps",
    "brew_boiler_temps",
    "pump_pressures",
    "flow_rates",
    "weights",
)


async def test_recorder_rows_lack_curve_arrays(
    recorder_mock, hass, init_integration, mock_xenia_api
):
    tracker = _get_tracker(hass, init_integration)
    tracker._is_brewing = True
    tracker._shot_start_time = dt_util.utcnow() - timedelta(seconds=25)
    await _drive_status(hass, mock_xenia_api, init_integration, MachineStatus.ON)
    tracker._afterflow_until = dt_util.utcnow() - timedelta(seconds=1)
    await _drive_status(hass, mock_xenia_api, init_integration, MachineStatus.ON)
    await hass.async_block_till_done()

    # the live entity still carries the full payload
    live_attrs = hass.states.get(TRACKER).attributes
    for attr in CURVE_ATTRS:
        assert live_attrs[attr]

    await async_wait_recording_done(hass)
    states = await get_instance(hass).async_add_executor_job(
        partial(
            history.get_significant_states,
            hass,
            dt_util.utcnow() - timedelta(minutes=5),
            None,
            [TRACKER],
            significant_changes_only=False,
        )
    )
    rows = states[TRACKER]
    assert rows
    for row in rows:
        for attr in CURVE_ATTRS:
            assert attr not in row.attributes
