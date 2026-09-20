"""Tests for __init__.py — setup, unload, and the execute_script service."""

from unittest.mock import patch

from homeassistant.const import ATTR_CONFIG_ENTRY_ID
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xenia_home import (
    ATTR_SCRIPT_ID,
    ATTR_SCRIPT_NAME,
    SERVICE_EXECUTE_SCRIPT,
)
from custom_components.xenia_home.const import CONF_POLL_IDLE, XENIA_DOMAIN
from custom_components.xenia_home.shot_store import XeniaShotStore
from tests.fixtures.api_responses import MACHINE_NEW_FW_FIELDS
from tests.fixtures.shots import shot_payload

# ===========================================================================
# Setup smoke
# ===========================================================================


async def test_async_setup_entry_loads_integration(init_integration):
    """The init_integration fixture itself asserts setup ran; this proves it."""
    assert init_integration.state.value == "loaded"


async def test_integration_registers_execute_script_service(hass, init_integration):
    assert hass.services.has_service(XENIA_DOMAIN, SERVICE_EXECUTE_SCRIPT)


async def test_runtime_data_holds_both_coordinators(hass, init_integration):
    rd = init_integration.runtime_data
    assert rd.coordinator is not None
    assert rd.config_coordinator is not None


# ===========================================================================
# execute_script service — tests the REAL registered closure
# ===========================================================================


async def test_execute_script_by_id_calls_xenia(hass, init_integration, mock_xenia_api):
    mock_xenia_api.expect_execute_script()
    await hass.services.async_call(
        XENIA_DOMAIN,
        SERVICE_EXECUTE_SCRIPT,
        {ATTR_SCRIPT_ID: 10},
        blocking=True,
    )
    await hass.async_block_till_done()
    mock_xenia_api.assert_post_called_with("scripts/execute", "10")


async def test_execute_script_by_name_resolves_id(
    hass, init_integration, mock_xenia_api
):
    mock_xenia_api.expect_execute_script()
    await hass.services.async_call(
        XENIA_DOMAIN,
        SERVICE_EXECUTE_SCRIPT,
        {ATTR_SCRIPT_NAME: "MyShot"},
        blocking=True,
    )
    await hass.async_block_till_done()
    # Default SCRIPTS_PAYLOAD maps MyShot -> 10
    mock_xenia_api.assert_post_called_with("scripts/execute", "10")


async def test_execute_script_by_builtin_name_works(
    hass, init_integration, mock_xenia_api
):
    mock_xenia_api.expect_execute_script()
    await hass.services.async_call(
        XENIA_DOMAIN,
        SERVICE_EXECUTE_SCRIPT,
        {ATTR_SCRIPT_NAME: "Espresso"},
        blocking=True,
    )
    await hass.async_block_till_done()
    # BUILTIN_SCRIPTS maps Espresso -> 1
    mock_xenia_api.assert_post_called_with("scripts/execute", "1")


async def test_execute_script_with_no_args_raises_validation_error(
    hass, init_integration
):
    with pytest.raises(ServiceValidationError) as exc_info:
        await hass.services.async_call(
            XENIA_DOMAIN, SERVICE_EXECUTE_SCRIPT, {}, blocking=True
        )
    assert exc_info.value.translation_key == "script_required"


async def test_execute_script_with_unknown_name_raises_validation_error(
    hass, init_integration
):
    with pytest.raises(ServiceValidationError) as exc_info:
        await hass.services.async_call(
            XENIA_DOMAIN,
            SERVICE_EXECUTE_SCRIPT,
            {ATTR_SCRIPT_NAME: "Ghost"},
            blocking=True,
        )
    assert exc_info.value.translation_key == "script_not_found"


async def test_execute_script_id_takes_priority_over_name(
    hass, init_integration, mock_xenia_api
):
    mock_xenia_api.expect_execute_script()
    await hass.services.async_call(
        XENIA_DOMAIN,
        SERVICE_EXECUTE_SCRIPT,
        {ATTR_SCRIPT_ID: 2, ATTR_SCRIPT_NAME: "MyShot"},
        blocking=True,
    )
    await hass.async_block_till_done()
    # ID 2 (Espresso endless) wins over name MyShot (would be 10)
    mock_xenia_api.assert_post_called_with("scripts/execute", "2")


# ===========================================================================
# Unload
# ===========================================================================


async def test_unload_entry_keeps_service_registered(hass, init_integration):
    # async_setup (which registers the service) runs once per HA run, so the
    # service must survive an unload/reload of the only entry.
    assert hass.services.has_service(XENIA_DOMAIN, SERVICE_EXECUTE_SCRIPT)
    await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert hass.services.has_service(XENIA_DOMAIN, SERVICE_EXECUTE_SCRIPT)

    with pytest.raises(ServiceValidationError) as exc_info:
        await hass.services.async_call(
            XENIA_DOMAIN,
            SERVICE_EXECUTE_SCRIPT,
            {ATTR_SCRIPT_ID: 10},
            blocking=True,
        )
    assert exc_info.value.translation_key == "entry_not_loaded"


async def _add_second_entry(hass, mock_xenia_api) -> MockConfigEntry:
    second = MockConfigEntry(
        domain=XENIA_DOMAIN,
        title="xenia2.local",
        unique_id="xenia2.local",
        data={"host": "xenia2.local"},
        options={},
    )
    for endpoint in ("overview", "overview_single", "machine", "switches"):
        mock_xenia_api._mock.get(
            f"http://xenia2.local/api/v2/{endpoint}",
            payload={"MA_STATUS": 1} if endpoint == "overview" else {},
            repeat=True,
        )
    mock_xenia_api._mock.get(
        "http://xenia2.local/api/v2/scripts/list",
        payload={"index_list": [], "title_list": []},
        repeat=True,
    )
    second.add_to_hass(hass)
    await hass.config_entries.async_setup(second.entry_id)
    await hass.async_block_till_done()
    return second


async def test_unload_entry_keeps_service_when_other_entries_remain(
    hass, init_integration, mock_xenia_api
):
    await _add_second_entry(hass, mock_xenia_api)
    await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert hass.services.has_service(XENIA_DOMAIN, SERVICE_EXECUTE_SCRIPT)


# ===========================================================================
# execute_script: addressing a machine and machine errors
# ===========================================================================


async def test_execute_script_raises_translated_error_when_machine_refuses(
    hass, init_integration, mock_xenia_api
):
    mock_xenia_api.fail_post("scripts/execute")
    with pytest.raises(HomeAssistantError) as exc_info:
        await hass.services.async_call(
            XENIA_DOMAIN, SERVICE_EXECUTE_SCRIPT, {ATTR_SCRIPT_ID: 10}, blocking=True
        )
    assert exc_info.value.translation_key == "write_failed"


async def test_execute_script_with_unknown_config_entry_id(hass, init_integration):
    with pytest.raises(ServiceValidationError) as exc_info:
        await hass.services.async_call(
            XENIA_DOMAIN,
            SERVICE_EXECUTE_SCRIPT,
            {ATTR_CONFIG_ENTRY_ID: "nope", ATTR_SCRIPT_ID: 10},
            blocking=True,
        )
    assert exc_info.value.translation_key == "entry_not_found"


async def test_execute_script_with_unloaded_config_entry_id(hass, init_integration):
    await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    with pytest.raises(ServiceValidationError) as exc_info:
        await hass.services.async_call(
            XENIA_DOMAIN,
            SERVICE_EXECUTE_SCRIPT,
            {ATTR_CONFIG_ENTRY_ID: init_integration.entry_id, ATTR_SCRIPT_ID: 10},
            blocking=True,
        )
    assert exc_info.value.translation_key == "entry_not_loaded"


async def test_execute_script_needs_config_entry_id_with_several_machines(
    hass, init_integration, mock_xenia_api
):
    await _add_second_entry(hass, mock_xenia_api)
    with pytest.raises(ServiceValidationError) as exc_info:
        await hass.services.async_call(
            XENIA_DOMAIN, SERVICE_EXECUTE_SCRIPT, {ATTR_SCRIPT_ID: 10}, blocking=True
        )
    assert exc_info.value.translation_key == "multiple_entries"


async def test_execute_script_config_entry_id_picks_the_machine(
    hass, init_integration, mock_xenia_api
):
    second = await _add_second_entry(hass, mock_xenia_api)
    mock_xenia_api._mock.post(
        "http://xenia2.local/api/v2/scripts/execute", status=200, repeat=True
    )
    await hass.services.async_call(
        XENIA_DOMAIN,
        SERVICE_EXECUTE_SCRIPT,
        {ATTR_CONFIG_ENTRY_ID: second.entry_id, ATTR_SCRIPT_ID: 1},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert mock_xenia_api.post_count("scripts/execute") == 0


# ===========================================================================
# Device info
# ===========================================================================


async def test_device_info_serial_and_mac_new_firmware(
    hass, enable_custom_integrations, mock_xenia_api, mock_config_entry
):
    mock_xenia_api.set_machine(**MACHINE_NEW_FW_FIELDS)
    mock_xenia_api.register()
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device(
        identifiers={("xenia_home", "xenia.local")}
    )
    assert device is not None
    assert device.serial_number == "300200000000"
    assert (dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff") in device.connections


async def test_device_info_old_firmware_has_no_serial(hass, init_integration):
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device(
        identifiers={("xenia_home", "xenia.local")}
    )
    assert device is not None
    assert device.serial_number is None
    assert (dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff") in device.connections


# ===========================================================================
# Removal
# ===========================================================================


async def test_remove_entry_deletes_shot_storage(hass, init_integration):
    store = init_integration.runtime_data.shot_store
    await store.async_add_shot(shot_payload())
    await store.async_set_migrated()
    assert store.list_shots() != []
    assert store.migrated is True
    entry_id = init_integration.entry_id

    await hass.config_entries.async_remove(entry_id)
    await hass.async_block_till_done()

    fresh_store = XeniaShotStore(hass, entry_id)
    await fresh_store.async_load()
    assert fresh_store.list_shots() == []
    assert fresh_store.migrated is False


# ===========================================================================
# Options update listener
# ===========================================================================


async def test_options_change_reloads_entry(hass, init_integration):
    with patch.object(
        hass.config_entries, "async_reload", wraps=hass.config_entries.async_reload
    ) as reload:
        hass.config_entries.async_update_entry(
            init_integration,
            options={**init_integration.options, CONF_POLL_IDLE: 5.0},
        )
        await hass.async_block_till_done()
    reload.assert_called_once_with(init_integration.entry_id)
