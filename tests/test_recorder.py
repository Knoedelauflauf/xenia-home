"""The recorder must not persist the shot curve arrays."""

import asyncio
from datetime import timedelta
from functools import partial
from unittest.mock import patch

import pytest
from homeassistant.components.recorder import get_instance, history
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.xenia_home.const import XENIA_DOMAIN
from custom_components.xenia_home.recorder_import import async_import_recorder_shots
from custom_components.xenia_home.shot_store import XeniaShotStore
from custom_components.xenia_home.xenia import MachineStatus
from tests.fixtures.shots import shot_payload
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


async def _seed_legacy_recorder_rows(hass, *payloads):
    """Emulate rows an old integration version left in the recorder."""
    for payload in payloads:
        hass.states.async_set(
            TRACKER,
            payload["start_time"],
            {"event_type": "shot_completed", **payload},
        )
    await async_wait_recording_done(hass)


async def test_migration_imports_legacy_shots_once(
    recorder_mock, hass, enable_custom_integrations, mock_config_entry, mock_xenia_api
):
    # simulate an existing install: the entity registry already maps the
    # tracker's unique_id to TRACKER, the way a real upgrade would
    mock_config_entry.add_to_hass(hass)
    registry = er.async_get(hass)
    registry_entry = registry.async_get_or_create(
        "event",
        XENIA_DOMAIN,
        f"{XENIA_DOMAIN}_shot_tracker_{mock_config_entry.data['host']}",
        suggested_object_id="xenia_espresso_machine_shot_tracker",
        config_entry=mock_config_entry,
    )
    assert registry_entry.entity_id == TRACKER

    legacy = shot_payload("2026-07-10T09:00:00.000+00:00")
    # the old integration recorded every attribute change; the last row per
    # start_time carries the complete payload
    partial_row = {**legacy, "weights": legacy["weights"][:1]}
    await _seed_legacy_recorder_rows(hass, partial_row, legacy)

    mock_xenia_api.register()
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    store = mock_config_entry.runtime_data.shot_store
    summaries = store.list_shots()
    assert [s["shot_id"] for s in summaries] == [legacy["start_time"]]
    shots = await store.async_get_shots([legacy["start_time"]])
    assert shots[0]["weights"] == legacy["weights"]

    # reload: the import must not run again nor duplicate anything
    await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(mock_config_entry.runtime_data.shot_store.list_shots()) == 1


async def test_setup_without_recorder_starts_empty(hass, init_integration):
    await hass.async_block_till_done(wait_background_tasks=True)
    store = init_integration.runtime_data.shot_store
    assert store.list_shots() == []
    assert store.migrated


async def _store_with_tracker_entity(hass, mock_config_entry):
    """A loaded store plus a registered event entity, as a real upgrade has."""
    mock_config_entry.add_to_hass(hass)
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "event",
        XENIA_DOMAIN,
        f"{XENIA_DOMAIN}_shot_tracker_{mock_config_entry.data['host']}",
        config_entry=mock_config_entry,
    )
    hass.config.components.add("recorder")
    store = XeniaShotStore(hass, mock_config_entry.entry_id)
    await store.async_load()
    return store


async def test_cancelled_import_leaves_migrated_false(hass, mock_config_entry):
    store = await _store_with_tracker_entity(hass, mock_config_entry)
    entered = asyncio.Event()

    async def _hang(*_args, **_kwargs):
        entered.set()
        await asyncio.Event().wait()  # never resolves; only cancellation ends this

    with patch(
        "custom_components.xenia_home.recorder_import._legacy_shots", side_effect=_hang
    ):
        task = hass.async_create_task(
            async_import_recorder_shots(hass, mock_config_entry, store),
            "test_cancelled_import",
        )
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert store.migrated is False


async def test_genuine_failure_still_marks_migrated(hass, mock_config_entry):
    store = await _store_with_tracker_entity(hass, mock_config_entry)

    with patch(
        "custom_components.xenia_home.recorder_import._legacy_shots",
        side_effect=RuntimeError("boom"),
    ):
        await async_import_recorder_shots(hass, mock_config_entry, store)

    assert store.migrated is True
