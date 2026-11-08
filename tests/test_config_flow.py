"""Tests for config_flow.py — config and options flows."""

from unittest.mock import patch

from homeassistant import config_entries, data_entry_flow
import pytest

from custom_components.xenia_home.config_flow import CREATE_NEW_SCRIPT
from custom_components.xenia_home.const import (
    CONF_MANAGED_SCRIPT_ID,
    CONF_WEIGHT_MANAGEMENT_ENABLED,
    CONF_WEIGHT_MAX,
    CONF_WEIGHT_MIN,
    CONF_WEIGHT_STEP,
    DEFAULT_SCRIPT_NAME,
    XENIA_DOMAIN,
)

# ===========================================================================
# Config flow — user step
# ===========================================================================


async def test_user_step_shows_form_initially(
    hass, enable_custom_integrations, mock_xenia_api
):
    result = await hass.config_entries.flow.async_init(
        XENIA_DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_user_step_creates_entry_on_successful_connection(
    hass, enable_custom_integrations, mock_xenia_api
):
    result = await hass.config_entries.flow.async_init(
        XENIA_DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"host": "xenia.local"}
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {"host": "xenia.local"}


async def test_user_step_aborts_when_already_configured(
    hass, enable_custom_integrations, mock_xenia_api, mock_config_entry
):
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        XENIA_DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"host": "xenia.local"}
    )
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.parametrize(
    "exception",
    [TimeoutError("timeout"), OSError("refused")],
)
async def test_user_step_shows_cannot_connect_on_network_error(
    hass, enable_custom_integrations, mock_xenia_api, exception
):
    mock_xenia_api.for_host("bad.host").override("get", "overview", exc=exception)
    result = await hass.config_entries.flow.async_init(
        XENIA_DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"host": "bad.host"}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


# ===========================================================================
# Config flow — reconfigure step
# ===========================================================================


async def test_reconfigure_updates_host_on_success(
    hass, enable_custom_integrations, mock_xenia_api, mock_config_entry
):
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    new_machine = mock_xenia_api.for_host("new.host")

    result = await mock_config_entry.start_reconfigure_flow(hass)
    with patch.object(
        hass.config_entries, "async_reload", wraps=hass.config_entries.async_reload
    ) as reload:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={"host": "  new.host  "}
        )
        await hass.async_block_till_done()
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data["host"] == "new.host"
    reload.assert_called_once_with(mock_config_entry.entry_id)
    assert mock_config_entry.state is config_entries.ConfigEntryState.LOADED
    assert new_machine.bodies("get", "overview")


async def test_reconfigure_shows_error_on_connection_failure(
    hass, enable_custom_integrations, mock_xenia_api, mock_config_entry
):
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    mock_xenia_api.for_host("bad.host").override(
        "get", "overview", exc=OSError("refused")
    )
    result = await mock_config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"host": "bad.host"}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


# ===========================================================================
# Options flow — init step (toggle gates)
# ===========================================================================


async def test_options_init_shows_form_when_no_input(hass, init_integration):
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "init"


async def test_options_disable_weight_creates_entry(hass, init_integration):
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_WEIGHT_MANAGEMENT_ENABLED: False,
        },
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_WEIGHT_MANAGEMENT_ENABLED] is False
    assert result["data"][CONF_MANAGED_SCRIPT_ID] is None


# ===========================================================================
# Options flow — select_script step
# ===========================================================================


async def test_options_select_script_shows_weight_scripts_only(
    hass, init_integration, mock_xenia_api
):
    mock_xenia_api.set_scripts({10: "WithWeight", 20: "NoWeight"})
    mock_xenia_api.set_script(10, "1;13;27 45;7;", "WithWeight")
    mock_xenia_api.set_script(20, "1;13;7;", "NoWeight")

    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_WEIGHT_MANAGEMENT_ENABLED: True,
        },
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "select_script"


async def test_options_select_existing_script_proceeds_to_configure_weight(
    hass, init_integration, mock_xenia_api
):
    mock_xenia_api.set_script(10, "1;13;27 45;7;", "MyShot")
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_WEIGHT_MANAGEMENT_ENABLED: True,
        },
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={CONF_MANAGED_SCRIPT_ID: "10"}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "configure_weight"


async def test_options_create_new_script_calls_api(
    hass, enable_custom_integrations, mock_xenia_api, mock_config_entry
):
    mock_xenia_api.set_scripts({25: DEFAULT_SCRIPT_NAME})
    mock_xenia_api.set_script(10, "1;13;27 45;7;", "MyShot")

    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_WEIGHT_MANAGEMENT_ENABLED: True,
        },
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={CONF_MANAGED_SCRIPT_ID: CREATE_NEW_SCRIPT}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "configure_weight"
    mock_xenia_api.assert_post_called_with("scripts/create", DEFAULT_SCRIPT_NAME)


# ===========================================================================
# Options flow — configure_weight step
# ===========================================================================


async def test_options_configure_weight_creates_entry(
    hass, init_integration, mock_xenia_api
):
    mock_xenia_api.set_script(10, "1;13;27 45;7;", "MyShot")
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_WEIGHT_MANAGEMENT_ENABLED: True,
        },
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={CONF_MANAGED_SCRIPT_ID: "10"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_WEIGHT_MIN: 20.0,
            CONF_WEIGHT_MAX: 45.0,
            CONF_WEIGHT_STEP: 0.1,
        },
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[CONF_WEIGHT_MANAGEMENT_ENABLED] is True
    assert data[CONF_MANAGED_SCRIPT_ID] == 10
    assert data[CONF_WEIGHT_MIN] == 20.0
    assert data[CONF_WEIGHT_MAX] == 45.0
    assert data[CONF_WEIGHT_STEP] == 0.1


# ===========================================================================
# Full end-to-end: weight
# ===========================================================================


async def test_options_full_flow_weight(hass, init_integration, mock_xenia_api):
    mock_xenia_api.set_script(10, "1;13;27 45;7;", "MyShot")
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_WEIGHT_MANAGEMENT_ENABLED: True},
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={CONF_MANAGED_SCRIPT_ID: "10"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_WEIGHT_MIN: 25.0,
            CONF_WEIGHT_MAX: 50.0,
            CONF_WEIGHT_STEP: 0.5,
        },
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[CONF_MANAGED_SCRIPT_ID] == 10
    assert data[CONF_WEIGHT_MIN] == 25.0
