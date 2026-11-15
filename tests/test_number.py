"""Tests for the setpoint and weight target numbers."""

from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from syrupy.assertion import SnapshotAssertion

from custom_components.xenia_home.const import (
    CONF_MANAGED_SCRIPT_ID,
    CONF_WEIGHT_MANAGEMENT_ENABLED,
    CONF_WEIGHT_MAX,
    CONF_WEIGHT_MIN,
    CONF_WEIGHT_STEP,
)

from tests import setup_integration
from tests.conftest import MockXeniaApi

BREW_GROUP = "number.xenia_espresso_machine_brewgroup_set_temperature"
BREW_BOILER = "number.xenia_espresso_machine_brewboiler_set_temperature"
WEIGHT = "number.xenia_espresso_machine_script_weight_target"


async def _set(hass: HomeAssistant, entity_id: str, value: float) -> None:
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: value},
        blocking=True,
    )


@pytest.fixture
async def init_with_weight(
    hass: HomeAssistant,
    mock_xenia_api: MockXeniaApi,
    mock_config_entry_factory_with_options,
) -> MockConfigEntry:
    """Set up a machine that manages the weight target of script 17."""
    mock_xenia_api.set_script(17, "1;13;27 45;7;", "Test Shot")
    entry = mock_config_entry_factory_with_options(
        {
            CONF_WEIGHT_MANAGEMENT_ENABLED: True,
            CONF_MANAGED_SCRIPT_ID: 17,
            CONF_WEIGHT_MIN: 25.0,
            CONF_WEIGHT_MAX: 50.0,
            CONF_WEIGHT_STEP: 0.5,
        }
    )
    await setup_integration(hass, entry)
    return entry


async def test_number_entities_snapshot(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
) -> None:
    """The setpoints match the snapshot; without weight management there is no weight target."""
    for entity_id in (BREW_GROUP, BREW_BOILER):
        assert hass.states.get(entity_id) == snapshot(name=f"{entity_id}-state")
        assert entity_registry.async_get(entity_id) == snapshot(
            name=f"{entity_id}-registry"
        )
    assert hass.states.get(WEIGHT) is None


@pytest.mark.parametrize(
    ("entity_id", "path", "body"),
    [
        (BREW_GROUP, "inc_dec", '{"BG_SET_TEMP":"93.5", "BB_SET_TEMP":"93.5"}'),
        (BREW_BOILER, "inc_dec_bb", '{"BB_SET_TEMP":"93.5"}'),
    ],
)
async def test_set_temperature(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    entity_id: str,
    path: str,
    body: str,
) -> None:
    """A setpoint is written to the machine and read back."""
    mock_xenia_api.set_overview_single(BG_SET_TEMP=93.5, BB_SET_TEMP=93.5)
    await _set(hass, entity_id, 93.5)
    assert mock_xenia_api.bodies("post", path) == [body]
    assert hass.states.get(entity_id).state == "93.5"


async def test_refused_temperature_raises_and_polls(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_xenia_api: MockXeniaApi
) -> None:
    """A refused setpoint raises a translated error and still polls the machine."""
    mock_xenia_api.fail("post", "inc_dec")
    polls = len(mock_xenia_api.bodies("get", "overview"))
    with pytest.raises(HomeAssistantError) as exc_info:
        await _set(hass, BREW_GROUP, 93.5)
    assert exc_info.value.translation_key == "write_failed"
    await hass.async_block_till_done()
    assert len(mock_xenia_api.bodies("get", "overview")) > polls


async def test_weight_target(
    hass: HomeAssistant, init_with_weight: MockConfigEntry
) -> None:
    """The weight target shows the managed script's target in the configured range."""
    state = hass.states.get(WEIGHT)
    assert state.state == "45.0"
    assert state.attributes["min"] == 25.0
    assert state.attributes["max"] == 50.0
    assert state.attributes["step"] == 0.5
    assert state.attributes["unit_of_measurement"] == "g"


async def test_set_weight_target_rewrites_the_script(
    hass: HomeAssistant, init_with_weight: MockConfigEntry, mock_xenia_api: MockXeniaApi
) -> None:
    """Setting the target rewrites the current script on the machine and reads it back."""
    mock_xenia_api.set_script(17, "1;13;3 70 5000;27 45;7;", "Test Shot")
    await _set(hass, WEIGHT, 38.5)
    assert mock_xenia_api.bodies("post", "scripts/create") == [
        '{"script_id":17,"Edit":"Enabled","switch":null,"script":"none",'
        '"name":"Test Shot","instruction":"1;13;3 70 5000;27 38.5;7;"}'
    ]
    assert len(mock_xenia_api.bodies("get", "scripts/list")) == 2


async def test_set_weight_target_of_deleted_script(
    hass: HomeAssistant, init_with_weight: MockConfigEntry, mock_xenia_api: MockXeniaApi
) -> None:
    """A script deleted on the machine is not recreated; the error says why."""
    mock_xenia_api.set_script(17, "", "")
    with pytest.raises(HomeAssistantError) as exc_info:
        await _set(hass, WEIGHT, 40.0)
    assert exc_info.value.translation_key == "managed_script_missing"
    assert mock_xenia_api.bodies("post", "scripts/create") == []


async def test_weight_target_of_unreadable_script(
    hass: HomeAssistant, init_with_weight: MockConfigEntry, mock_xenia_api: MockXeniaApi
) -> None:
    """A script with commands the parser does not know shows no target and is kept."""
    mock_xenia_api.set_script(17, "1;13;x;27 45;7;", "Test Shot")
    await hass.config_entries.async_reload(init_with_weight.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(WEIGHT).state == "unknown"

    with pytest.raises(HomeAssistantError) as exc_info:
        await _set(hass, WEIGHT, 40.0)
    assert exc_info.value.translation_key == "managed_script_unreadable"
    assert mock_xenia_api.bodies("post", "scripts/create") == []


@pytest.mark.parametrize("path", ["scripts/read", "scripts/create"])
async def test_refused_weight_target_raises(
    hass: HomeAssistant,
    init_with_weight: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    path: str,
) -> None:
    """A refused read or write raises a translated error."""
    mock_xenia_api.fail("post", path)
    with pytest.raises(HomeAssistantError) as exc_info:
        await _set(hass, WEIGHT, 40.0)
    assert exc_info.value.translation_key == "write_failed"
