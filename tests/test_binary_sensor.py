"""Tests for the water tank sensor."""

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from syrupy.assertion import SnapshotAssertion

from tests import setup_integration
from tests.conftest import MockXeniaApi

WATER_TANK = "binary_sensor.xenia_espresso_machine_water_tank_empty"


async def test_binary_sensor_entities_snapshot(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
) -> None:
    """The water tank sensor matches the snapshot."""
    assert hass.states.get(WATER_TANK) == snapshot(name=f"{WATER_TANK}-state")
    assert entity_registry.async_get(WATER_TANK) == snapshot(
        name=f"{WATER_TANK}-registry"
    )


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        (1, STATE_OFF),
        (2, STATE_ON),
        (0, STATE_OFF),
        (99, STATE_OFF),
        (None, STATE_UNKNOWN),
    ],
)
async def test_water_tank(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    level: int | None,
    expected: str,
) -> None:
    """Level 2 means the tank is empty, any other level does not; none is unknown."""
    mock_xenia_api.set_overview_single(PU_SENS_WATER_TANK_LEVEL=level)
    await setup_integration(hass, mock_config_entry)
    assert hass.states.get(WATER_TANK).state == expected
