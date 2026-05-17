"""Tests for config_flow.py — config and options flows."""

from __future__ import annotations

import pytest
from homeassistant import config_entries, data_entry_flow

from custom_components.xenia_home.config_flow import CREATE_NEW_SCRIPT
from custom_components.xenia_home.const import (
    CONF_CONFIGURE_POLLING,
    CONF_MANAGED_SCRIPT_ID,
    CONF_POLL_ACTIVE,
    CONF_POLL_BREWING,
    CONF_POLL_IDLE,
    CONF_POLL_READY,
    CONF_READY_THRESHOLD,
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
    mock_xenia_api.register()
    result = await hass.config_entries.flow.async_init(
        XENIA_DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_user_step_creates_entry_on_successful_connection(
    hass, enable_custom_integrations, mock_xenia_api
):
    mock_xenia_api.register()
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
    mock_xenia_api.register()
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
    # Make the GET /overview to bad.host raise
    mock_xenia_api._mock.get(
        "http://bad.host/api/v2/overview", exception=exception, repeat=True
    )
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
    mock_xenia_api.register()
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Mock the new host's overview
    mock_xenia_api._mock.get(
        "http://new.host/api/v2/overview",
        payload={"MA_STATUS": 1},
        repeat=True,
    )

    result = await mock_config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"host": "  new.host  "}
    )
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data["host"] == "new.host"


async def test_reconfigure_shows_error_on_connection_failure(
    hass, enable_custom_integrations, mock_xenia_api, mock_config_entry
):
    mock_xenia_api.register()
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    mock_xenia_api._mock.get(
        "http://bad.host/api/v2/overview",
        exception=OSError("refused"),
        repeat=True,
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


async def test_options_disable_weight_and_polling_creates_entry(hass, init_integration):
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_WEIGHT_MANAGEMENT_ENABLED: False,
            CONF_CONFIGURE_POLLING: False,
        },
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_WEIGHT_MANAGEMENT_ENABLED] is False
    assert result["data"][CONF_MANAGED_SCRIPT_ID] is None


async def test_options_enable_polling_only_shows_polling_form(hass, init_integration):
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_WEIGHT_MANAGEMENT_ENABLED: False,
            CONF_CONFIGURE_POLLING: True,
        },
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "configure_polling"


async def test_options_disabling_polling_strips_polling_keys(
    hass,
    enable_custom_integrations,
    mock_xenia_api,
    mock_config_entry_factory_with_options,
):
    entry = mock_config_entry_factory_with_options(
        {
            CONF_POLL_BREWING: 0.5,
            CONF_POLL_IDLE: 10.0,
            CONF_READY_THRESHOLD: 3.0,
        }
    )
    mock_xenia_api.register()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_WEIGHT_MANAGEMENT_ENABLED: False,
            CONF_CONFIGURE_POLLING: False,
        },
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert CONF_POLL_BREWING not in result["data"]
    assert CONF_POLL_IDLE not in result["data"]
    assert CONF_READY_THRESHOLD not in result["data"]


# ===========================================================================
# Options flow — select_script step
# ===========================================================================


async def test_options_select_script_shows_weight_scripts_only(
    hass, init_integration, mock_xenia_api
):
    # The flow re-reads scripts on entry to select_script via Xenia.get_scripts
    # and Xenia.read_script. Register them.
    mock_xenia_api._mock.get(
        mock_xenia_api._url("scripts/list"),
        payload={"index_list": [10, 20], "title_list": ["WithWeight", "NoWeight"]},
        repeat=True,
    )
    # Two POSTs to /scripts/read — registrations are popped FIFO
    mock_xenia_api._mock.post(
        mock_xenia_api._url("scripts/read"),
        payload={"Content": "1;13;27 45;7;", "Title": "WithWeight"},
    )
    mock_xenia_api._mock.post(
        mock_xenia_api._url("scripts/read"),
        payload={"Content": "1;13;7;", "Title": "NoWeight"},
    )

    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_WEIGHT_MANAGEMENT_ENABLED: True,
            CONF_CONFIGURE_POLLING: False,
        },
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "select_script"


async def test_options_select_existing_script_proceeds_to_configure_weight(
    hass, init_integration, mock_xenia_api
):
    mock_xenia_api._mock.post(
        mock_xenia_api._url("scripts/read"),
        payload={"Content": "1;13;27 45;7;", "Title": "MyShot"},
        repeat=True,
    )
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_WEIGHT_MANAGEMENT_ENABLED: True,
            CONF_CONFIGURE_POLLING: False,
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
    # scripts/list must return DEFAULT_SCRIPT_NAME after create_script is called.
    # Set this before register() so the repeat=True response is correct from
    # the start — aioresponses ignores later registrations when repeat=True
    # is already in effect for a URL.
    mock_xenia_api.set_scripts({25: DEFAULT_SCRIPT_NAME})
    mock_xenia_api.register()
    mock_xenia_api.expect_create_script()
    mock_xenia_api._mock.post(
        mock_xenia_api._url("scripts/read"),
        payload={"Content": "1;13;27 45;7;", "Title": "MyShot"},
        repeat=True,
    )

    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_WEIGHT_MANAGEMENT_ENABLED: True,
            CONF_CONFIGURE_POLLING: False,
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
    mock_xenia_api._mock.post(
        mock_xenia_api._url("scripts/read"),
        payload={"Content": "1;13;27 45;7;", "Title": "MyShot"},
        repeat=True,
    )
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_WEIGHT_MANAGEMENT_ENABLED: True,
            CONF_CONFIGURE_POLLING: False,
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
# Options flow — configure_polling step
# ===========================================================================


async def test_options_configure_polling_creates_entry_with_values(
    hass, init_integration
):
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_WEIGHT_MANAGEMENT_ENABLED: False,
            CONF_CONFIGURE_POLLING: True,
        },
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_POLL_BREWING: 0.5,
            CONF_POLL_ACTIVE: 2.0,
            CONF_POLL_READY: 5.0,
            CONF_POLL_IDLE: 10.0,
            CONF_READY_THRESHOLD: 3.0,
        },
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[CONF_POLL_BREWING] == 0.5
    assert data[CONF_READY_THRESHOLD] == 3.0


# ===========================================================================
# Full end-to-end: weight + polling
# ===========================================================================


async def test_options_full_flow_weight_and_polling(
    hass, init_integration, mock_xenia_api
):
    mock_xenia_api._mock.post(
        mock_xenia_api._url("scripts/read"),
        payload={"Content": "1;13;27 45;7;", "Title": "MyShot"},
        repeat=True,
    )
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_WEIGHT_MANAGEMENT_ENABLED: True,
            CONF_CONFIGURE_POLLING: True,
        },
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
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "configure_polling"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_POLL_BREWING: 0.5,
            CONF_POLL_ACTIVE: 2.0,
            CONF_POLL_READY: 5.0,
            CONF_POLL_IDLE: 10.0,
            CONF_READY_THRESHOLD: 3.0,
        },
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[CONF_MANAGED_SCRIPT_ID] == 10
    assert data[CONF_WEIGHT_MIN] == 25.0
    assert data[CONF_POLL_BREWING] == 0.5
