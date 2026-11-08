"""Tests for the diagnostics."""

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator
from syrupy.assertion import SnapshotAssertion

from custom_components.xenia_home.const import CONF_WEIGHT_MIN

from tests import setup_integration
from tests.conftest import MockXeniaApi
from tests.fixtures.api_responses import MACHINE_NEW_FW_FIELDS
from tests.fixtures.shots import shot_payload


async def test_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_xenia_api: MockXeniaApi,
    mock_config_entry_factory_with_options,
    snapshot: SnapshotAssertion,
) -> None:
    """The diagnostics hold the machine data with host, serial and MAC redacted."""
    mock_xenia_api.set_machine(**MACHINE_NEW_FW_FIELDS)
    entry = mock_config_entry_factory_with_options({CONF_WEIGHT_MIN: 20.0})
    await setup_integration(hass, entry)
    await entry.runtime_data.shot_store.async_add_shot(
        shot_payload("2026-07-01T10:00:00.000+00:00")
    )
    assert await get_diagnostics_for_config_entry(hass, hass_client, entry) == snapshot
