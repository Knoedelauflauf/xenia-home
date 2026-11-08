"""Tests for setting up, unloading and removing the integration."""

from typing import Any

from homeassistant.components.select import (
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_CONFIG_ENTRY_ID, ATTR_ENTITY_ID, ATTR_OPTION
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xenia_home.const import (
    CONF_POWER_ON_BEHAVIOR,
    CONF_WEIGHT_MIN,
    XENIA_DOMAIN,
    PowerOnBehavior,
)
from custom_components.xenia_home.services import (
    ATTR_SCRIPT_ID,
    ATTR_SCRIPT_NAME,
    SERVICE_EXECUTE_SCRIPT,
)

from tests import setup_integration, setup_second_machine
from tests.conftest import MockXeniaApi
from tests.fixtures.api_responses import MACHINE_NEW_FW_FIELDS

POWER_ON_BEHAVIOR = "select.xenia_espresso_machine_power_on_behavior"


async def _execute_script(hass: HomeAssistant, data: dict[str, Any]) -> None:
    await hass.services.async_call(
        XENIA_DOMAIN, SERVICE_EXECUTE_SCRIPT, data, blocking=True
    )


async def test_unload_and_reload(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The entry unloads cleanly and keeps the action registered."""
    assert await hass.config_entries.async_unload(init_integration.entry_id)
    assert init_integration.state is ConfigEntryState.NOT_LOADED
    assert hass.services.has_service(XENIA_DOMAIN, SERVICE_EXECUTE_SCRIPT)

    assert await hass.config_entries.async_setup(init_integration.entry_id)
    assert init_integration.state is ConfigEntryState.LOADED


async def test_device_of_old_firmware(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    init_integration: MockConfigEntry,
) -> None:
    """Old firmware reports no serial number; the MAC address links the device."""
    [device] = dr.async_entries_for_config_entry(
        device_registry, init_integration.entry_id
    )
    assert device.identifiers == {(XENIA_DOMAIN, "xenia.local")}
    assert device.manufacturer == "Xenia Espresso GmbH"
    assert device.sw_version == "2.3/1.5"
    assert device.serial_number is None
    assert device.connections == {(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff")}


async def test_device_of_new_firmware(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
) -> None:
    """New firmware reports the serial number of the machine."""
    mock_xenia_api.set_machine(**MACHINE_NEW_FW_FIELDS)
    await setup_integration(hass, mock_config_entry)
    [device] = dr.async_entries_for_config_entry(
        device_registry, mock_config_entry.entry_id
    )
    assert device.serial_number == "300200000000"


async def test_entity_id_change_keeps_the_entity_working(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    init_integration: MockConfigEntry,
) -> None:
    """A renamed entity keeps its state and still reacts to actions."""
    entity_registry.async_update_entity(
        POWER_ON_BEHAVIOR, new_entity_id="select.coffee_steam"
    )
    await hass.async_block_till_done()
    assert hass.states.get(POWER_ON_BEHAVIOR) is None

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: "select.coffee_steam", ATTR_OPTION: PowerOnBehavior.STEAM_ON},
        blocking=True,
    )
    assert hass.states.get("select.coffee_steam").state == PowerOnBehavior.STEAM_ON


async def test_setup_drops_options_of_older_releases(
    hass: HomeAssistant, mock_config_entry_factory_with_options
) -> None:
    """Options older releases had are removed; the power on behavior moves to its select."""
    entry = mock_config_entry_factory_with_options(
        {
            "poll_interval_idle": 10.0,
            "ready_threshold": 3.0,
            CONF_POWER_ON_BEHAVIOR: PowerOnBehavior.STEAM_ON,
            CONF_WEIGHT_MIN: 20.0,
        }
    )
    await setup_integration(hass, entry)
    assert entry.options == {CONF_WEIGHT_MIN: 20.0}
    assert hass.states.get(POWER_ON_BEHAVIOR).state == PowerOnBehavior.STEAM_ON


async def test_remove_deletes_the_shot_history(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    init_integration: MockConfigEntry,
    poll,
) -> None:
    """Removing the machine deletes its stored shots."""
    for second in range(12):
        await poll(MA_STATUS=3, SCALE_WEIGHT=float(second))
    for _ in range(3):
        await poll(MA_STATUS=1, SCALE_WEIGHT=12.0)
    assert any(key.startswith(f"{XENIA_DOMAIN}/") for key in hass_storage)

    await hass.config_entries.async_remove(init_integration.entry_id)
    await hass.async_block_till_done()
    assert not any(key.startswith(f"{XENIA_DOMAIN}/") for key in hass_storage)


@pytest.mark.parametrize(
    ("data", "script_id"),
    [
        ({ATTR_SCRIPT_ID: 10}, 10),
        ({ATTR_SCRIPT_NAME: "MyShot"}, 10),
        ({ATTR_SCRIPT_NAME: "Espresso"}, 1),
        ({ATTR_SCRIPT_ID: 2, ATTR_SCRIPT_NAME: "MyShot"}, 2),
    ],
)
async def test_execute_script(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    data: dict[str, Any],
    script_id: int,
) -> None:
    """The action runs a script by id or by name; the id wins."""
    await _execute_script(hass, data)
    assert mock_xenia_api.bodies("post", "scripts/execute") == [f'{{"ID":{script_id}}}']


@pytest.mark.parametrize(
    ("data", "translation_key"),
    [
        ({}, "script_required"),
        ({ATTR_SCRIPT_NAME: "Ghost"}, "script_not_found"),
        (
            {ATTR_CONFIG_ENTRY_ID: "nope", ATTR_SCRIPT_ID: 10},
            "service_config_entry_not_found",
        ),
    ],
)
async def test_execute_script_rejects_invalid_calls(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    data: dict[str, Any],
    translation_key: str,
) -> None:
    """Calls without a script, with an unknown script or machine are rejected."""
    with pytest.raises(ServiceValidationError) as exc_info:
        await _execute_script(hass, data)
    assert exc_info.value.translation_key == translation_key


@pytest.mark.parametrize("address", [False, True])
async def test_execute_script_needs_a_loaded_machine(
    hass: HomeAssistant, init_integration: MockConfigEntry, address: bool
) -> None:
    """The action fails while the machine is not loaded."""
    await hass.config_entries.async_unload(init_integration.entry_id)
    data: dict[str, Any] = {ATTR_SCRIPT_ID: 10}
    if address:
        data[ATTR_CONFIG_ENTRY_ID] = init_integration.entry_id
    with pytest.raises(ServiceValidationError) as exc_info:
        await _execute_script(hass, data)
    assert exc_info.value.translation_key == "service_config_entry_not_loaded"


async def test_execute_script_with_several_machines(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_xenia_api: MockXeniaApi
) -> None:
    """With several machines the call has to name one, and only that one runs it."""
    second_machine = mock_xenia_api.for_host("xenia2.local")
    second = await setup_second_machine(hass)
    with pytest.raises(ServiceValidationError) as exc_info:
        await _execute_script(hass, {ATTR_SCRIPT_ID: 10})
    assert (
        exc_info.value.translation_key
        == "service_found_multiple_config_entry_for_domain"
    )

    await _execute_script(
        hass, {ATTR_CONFIG_ENTRY_ID: second.entry_id, ATTR_SCRIPT_ID: 1}
    )
    assert second_machine.bodies("post", "scripts/execute") == ['{"ID":1}']
    assert mock_xenia_api.bodies("post", "scripts/execute") == []


async def test_execute_script_refused_by_machine(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_xenia_api: MockXeniaApi
) -> None:
    """A refused request raises a translated error with the cause."""
    mock_xenia_api.fail("post", "scripts/execute")
    with pytest.raises(HomeAssistantError) as exc_info:
        await _execute_script(hass, {ATTR_SCRIPT_ID: 10})
    assert exc_info.value.translation_key == "write_failed"
    assert exc_info.value.translation_placeholders == {
        "error": "ClientResponseError: 500, message='Internal Server Error', "
        "url='http://xenia.local/api/v2/scripts/execute'"
    }
