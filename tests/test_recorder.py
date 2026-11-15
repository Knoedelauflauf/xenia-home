"""Tests for the recorder: curve arrays stay out, old shots are imported once."""

from datetime import timedelta
from functools import partial
from unittest.mock import patch

from homeassistant.components.recorder import get_instance, history
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.xenia_home.const import XENIA_DOMAIN

from tests import setup_integration
from tests.fixtures.shots import shot_payload
from tests.test_event import TRACKER, brew, end_brew

CURVE_ATTRS = (
    "timestamps",
    "brew_group_temps",
    "brew_boiler_temps",
    "pump_pressures",
    "flow_rates",
    "weights",
)
GET_SIGNIFICANT_STATES = (
    "homeassistant.components.recorder.history.get_significant_states"
)
LEGACY_SHOT = shot_payload("2026-07-10T09:00:00.000+00:00")


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    recorder_mock: None, enable_custom_integrations: None
) -> None:
    """Set the recorder up before Home Assistant, as it requires."""


@pytest.fixture
async def legacy_install(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
) -> MockConfigEntry:
    """Return an entry with a shot tracker and shots an older release recorded.

    Older releases recorded a row per attribute change; the last row of a shot
    holds all of it. A row without curves is not a shot.
    """
    mock_config_entry.add_to_hass(hass)
    entity_registry.async_get_or_create(
        "event",
        XENIA_DOMAIN,
        f"{mock_config_entry.unique_id}_shot_tracker",
        suggested_object_id="xenia_espresso_machine_shot_tracker",
        config_entry=mock_config_entry,
    )
    for payload in (
        {**LEGACY_SHOT, "weights": LEGACY_SHOT["weights"][:1]},
        LEGACY_SHOT,
        {**shot_payload("2026-07-11T09:00:00.000+00:00"), "timestamps": []},
    ):
        hass.states.async_set(
            TRACKER, payload["start_time"], {"event_type": "shot_completed", **payload}
        )
    await async_wait_recording_done(hass)
    return mock_config_entry


def _shot_ids(entry: MockConfigEntry) -> list[str]:
    return [shot["shot_id"] for shot in entry.runtime_data.shot_store.list_shots()]


async def _reload(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_recorder_rows_lack_curve_arrays(
    hass: HomeAssistant, init_integration: MockConfigEntry, poll
) -> None:
    """The live state carries the curves, the recorded rows do not."""
    await brew(poll, 12)
    await end_brew(poll, weight=18.0)
    live = hass.states.get(TRACKER).attributes
    assert all(live[attr] for attr in CURVE_ATTRS)

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
    assert states[TRACKER]
    for row in states[TRACKER]:
        assert not set(CURVE_ATTRS) & set(row.attributes)


async def test_legacy_shots_are_imported_once(
    hass: HomeAssistant, legacy_install: MockConfigEntry
) -> None:
    """Complete shots from the recorder are imported, and only on the first start."""
    await setup_integration(hass, legacy_install)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert _shot_ids(legacy_install) == [LEGACY_SHOT["start_time"]]
    store = legacy_install.runtime_data.shot_store
    [shot] = await store.async_get_shots([LEGACY_SHOT["start_time"]])
    assert shot["weights"] == LEGACY_SHOT["weights"]

    await store.async_delete_shot(LEGACY_SHOT["start_time"])
    await _reload(hass, legacy_install)
    assert _shot_ids(legacy_install) == []


async def test_import_waits_for_home_assistant_to_start(
    hass: HomeAssistant, legacy_install: MockConfigEntry
) -> None:
    """An import cut short by an unload before the start runs at the next start."""
    hass.set_state(CoreState.not_running)
    await setup_integration(hass, legacy_install)
    assert _shot_ids(legacy_install) == []
    await hass.config_entries.async_unload(legacy_install.entry_id)

    hass.set_state(CoreState.running)
    await _reload(hass, legacy_install)
    assert _shot_ids(legacy_install) == [LEGACY_SHOT["start_time"]]


async def test_import_without_shot_tracker_imports_nothing(
    hass: HomeAssistant,
    legacy_install: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Shots are only imported from the shot tracker of the entry."""
    hass.set_state(CoreState.not_running)
    await setup_integration(hass, legacy_install)
    entity_registry.async_remove(TRACKER)

    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert _shot_ids(legacy_install) == []


async def test_failed_import_is_not_retried(
    hass: HomeAssistant,
    legacy_install: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failing import is logged once and the integration works on without it."""
    with patch(GET_SIGNIFICANT_STATES, side_effect=RuntimeError("boom")):
        await setup_integration(hass, legacy_install)
        await hass.async_block_till_done(wait_background_tasks=True)
    assert "One-time shot import from the recorder failed" in caplog.text

    await _reload(hass, legacy_install)
    assert _shot_ids(legacy_install) == []


async def test_new_install_imports_nothing(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A new install starts with an empty shot history."""
    await setup_integration(hass, mock_config_entry)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert _shot_ids(mock_config_entry) == []
    assert "shot import" not in caplog.text
