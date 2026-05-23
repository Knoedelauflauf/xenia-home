"""Tests for __init__.py — setup, unload, and the execute_script service."""

from homeassistant.exceptions import ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xenia_home import (
    ATTR_SCRIPT_ID,
    ATTR_SCRIPT_NAME,
    SERVICE_EXECUTE_SCRIPT,
)
from custom_components.xenia_home.const import XENIA_DOMAIN

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
    with pytest.raises(ServiceValidationError, match="script_id or script_name"):
        await hass.services.async_call(
            XENIA_DOMAIN, SERVICE_EXECUTE_SCRIPT, {}, blocking=True
        )


async def test_execute_script_with_unknown_name_raises_validation_error(
    hass, init_integration
):
    with pytest.raises(ServiceValidationError, match="not found"):
        await hass.services.async_call(
            XENIA_DOMAIN,
            SERVICE_EXECUTE_SCRIPT,
            {ATTR_SCRIPT_NAME: "Ghost"},
            blocking=True,
        )


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


async def test_unload_entry_removes_service_when_last_entry_gone(
    hass, init_integration
):
    assert hass.services.has_service(XENIA_DOMAIN, SERVICE_EXECUTE_SCRIPT)
    await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert not hass.services.has_service(XENIA_DOMAIN, SERVICE_EXECUTE_SCRIPT)


async def test_unload_entry_keeps_service_when_other_entries_remain(
    hass, init_integration, mock_xenia_api
):
    # Register a second integration entry against a second host
    second = MockConfigEntry(
        domain=XENIA_DOMAIN,
        title="xenia2.local",
        unique_id="xenia2.local",
        data={"host": "xenia2.local"},
        options={},
    )
    # Mock the second host's API endpoints
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

    # Now unload the first — service must stay
    await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert hass.services.has_service(XENIA_DOMAIN, SERVICE_EXECUTE_SCRIPT)
