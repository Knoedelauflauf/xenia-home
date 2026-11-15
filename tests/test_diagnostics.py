"""Tests for the diagnostics."""

from typing import Any

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator
from syrupy.assertion import SnapshotAssertion

from custom_components.xenia_home.const import CONF_WEIGHT_MIN

from tests import setup_integration, stored_shots
from tests.conftest import MockXeniaApi
from tests.fixtures.shots import shot_payload


async def test_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_storage: dict[str, Any],
    mock_xenia_api: MockXeniaApi,
    mock_config_entry_factory_with_options,
    snapshot: SnapshotAssertion,
) -> None:
    """The diagnostics hold the machine data with host, serial and MAC redacted."""
    entry = mock_config_entry_factory_with_options({CONF_WEIGHT_MIN: 20.0})
    hass_storage.update(
        stored_shots(entry.entry_id, shot_payload("2026-07-01T10:00:00.000+00:00"))
    )
    await setup_integration(hass, entry)
    assert await get_diagnostics_for_config_entry(hass, hass_client, entry) == snapshot
