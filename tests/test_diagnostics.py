"""Tests for the diagnostics download."""

from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)

from custom_components.xenia_home.const import CONF_WEIGHT_MIN
from tests.fixtures.api_responses import MACHINE_NEW_FW_FIELDS
from tests.fixtures.shots import shot_payload


async def test_diagnostics(
    hass,
    hass_client,
    enable_custom_integrations,
    mock_xenia_api,
    mock_config_entry_factory_with_options,
    snapshot,
):
    mock_xenia_api.set_machine(**MACHINE_NEW_FW_FIELDS)
    mock_xenia_api.register()
    entry = mock_config_entry_factory_with_options({CONF_WEIGHT_MIN: 20.0})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await entry.runtime_data.shot_store.async_add_shot(
        shot_payload("2026-07-01T10:00:00.000+00:00")
    )
    assert await get_diagnostics_for_config_entry(hass, hass_client, entry) == snapshot
