"""Tests for config_flow.py — XeniaConfigFlow and XeniaOptionsFlow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.xenia_home.config_flow import (
    CREATE_NEW_SCRIPT,
    XeniaConfigFlow,
    XeniaOptionsFlow,
)
from custom_components.xenia_home.const import (
    CONF_MANAGED_SCRIPT_ID,
    CONF_WEIGHT_MANAGEMENT_ENABLED,
    CONF_WEIGHT_MAX,
    CONF_WEIGHT_MIN,
    CONF_WEIGHT_STEP,
    DEFAULT_HOST,
    DEFAULT_SCRIPT_NAME,
    DEFAULT_WEIGHT_MAX,
    DEFAULT_WEIGHT_MIN,
    DEFAULT_WEIGHT_STEP,
    XENIA_DOMAIN,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hass() -> MagicMock:
    hass = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.flow = MagicMock()
    hass.config_entries.async_get_entry = MagicMock(return_value=None)
    return hass


def _make_flow() -> XeniaConfigFlow:
    """Build a XeniaConfigFlow with a mocked hass."""
    flow = XeniaConfigFlow()
    flow.hass = _make_hass()
    flow.context = {}
    # async_set_unique_id and _abort_if_unique_id_configured are HA internals
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = MagicMock()
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
    flow.async_show_form = MagicMock(return_value={"type": "form"})
    flow.async_abort = MagicMock(return_value={"type": "abort"})
    return flow


# ===========================================================================
# _async_test_connection
# ===========================================================================


@pytest.mark.asyncio
async def test_async_test_connection_returns_none_when_connected() -> None:
    flow = _make_flow()
    with (
        patch("custom_components.xenia_home.config_flow.Xenia"),
        patch(
            "custom_components.xenia_home.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch("asyncio.wait_for", new_callable=AsyncMock, return_value=True),
    ):
        result = await flow._async_test_connection(flow.hass, "xenia.local")

    assert result is None


@pytest.mark.asyncio
async def test_async_test_connection_returns_cannot_connect_when_not_connected() -> (
    None
):
    flow = _make_flow()
    with (
        patch("custom_components.xenia_home.config_flow.Xenia"),
        patch(
            "custom_components.xenia_home.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch("asyncio.wait_for", new_callable=AsyncMock, return_value=False),
    ):
        result = await flow._async_test_connection(flow.hass, "xenia.local")

    assert result == "cannot_connect"


@pytest.mark.asyncio
async def test_async_test_connection_returns_cannot_connect_on_timeout() -> None:
    flow = _make_flow()
    with (
        patch("custom_components.xenia_home.config_flow.Xenia"),
        patch(
            "custom_components.xenia_home.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "asyncio.wait_for",
            new_callable=AsyncMock,
            side_effect=TimeoutError("timeout"),
        ),
    ):
        result = await flow._async_test_connection(flow.hass, "xenia.local")

    assert result == "cannot_connect"


@pytest.mark.asyncio
async def test_async_test_connection_returns_cannot_connect_on_os_error() -> None:
    flow = _make_flow()
    with (
        patch("custom_components.xenia_home.config_flow.Xenia"),
        patch(
            "custom_components.xenia_home.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "asyncio.wait_for",
            new_callable=AsyncMock,
            side_effect=OSError("connection refused"),
        ),
    ):
        result = await flow._async_test_connection(flow.hass, "xenia.local")

    assert result == "cannot_connect"


@pytest.mark.asyncio
async def test_async_test_connection_returns_cannot_connect_on_client_error() -> None:
    from aiohttp import ClientError

    flow = _make_flow()
    with (
        patch("custom_components.xenia_home.config_flow.Xenia"),
        patch(
            "custom_components.xenia_home.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "asyncio.wait_for",
            new_callable=AsyncMock,
            side_effect=ClientError("client error"),
        ),
    ):
        result = await flow._async_test_connection(flow.hass, "xenia.local")

    assert result == "cannot_connect"


# ===========================================================================
# async_step_user — no input (initial display)
# ===========================================================================


@pytest.mark.asyncio
async def test_step_user_shows_form_when_no_input() -> None:
    flow = _make_flow()
    await flow.async_step_user(user_input=None)
    flow.async_show_form.assert_called_once()
    assert flow.async_show_form.call_args[1]["step_id"] == "user"


# ===========================================================================
# async_step_user — successful connection
# ===========================================================================


@pytest.mark.asyncio
async def test_step_user_creates_entry_on_success() -> None:
    flow = _make_flow()
    with patch.object(
        flow, "_async_test_connection", new_callable=AsyncMock, return_value=None
    ):
        await flow.async_step_user(user_input={"host": "xenia.local"})

    flow.async_create_entry.assert_called_once()
    call_kwargs = flow.async_create_entry.call_args[1]
    assert call_kwargs["data"]["host"] == "xenia.local"


@pytest.mark.asyncio
async def test_step_user_sets_unique_id_to_host() -> None:
    flow = _make_flow()
    with patch.object(
        flow, "_async_test_connection", new_callable=AsyncMock, return_value=None
    ):
        await flow.async_step_user(user_input={"host": "192.168.1.100"})

    flow.async_set_unique_id.assert_called_once_with("192.168.1.100")


@pytest.mark.asyncio
async def test_step_user_aborts_if_already_configured() -> None:
    flow = _make_flow()
    flow._abort_if_unique_id_configured = MagicMock(
        side_effect=Exception("already_configured")
    )
    with pytest.raises(Exception, match="already_configured"):
        with patch.object(
            flow, "_async_test_connection", new_callable=AsyncMock, return_value=None
        ):
            await flow.async_step_user(user_input={"host": "xenia.local"})


# ===========================================================================
# async_step_user — connection failure
# ===========================================================================


@pytest.mark.asyncio
async def test_step_user_shows_form_with_error_on_cannot_connect() -> None:
    flow = _make_flow()
    with patch.object(
        flow,
        "_async_test_connection",
        new_callable=AsyncMock,
        return_value="cannot_connect",
    ):
        await flow.async_step_user(user_input={"host": "bad.host"})

    flow.async_show_form.assert_called_once()
    errors = flow.async_show_form.call_args[1]["errors"]
    assert errors.get("base") == "cannot_connect"


@pytest.mark.asyncio
async def test_step_user_does_not_create_entry_on_connection_failure() -> None:
    flow = _make_flow()
    with patch.object(
        flow,
        "_async_test_connection",
        new_callable=AsyncMock,
        return_value="cannot_connect",
    ):
        await flow.async_step_user(user_input={"host": "bad.host"})

    flow.async_create_entry.assert_not_called()


# ===========================================================================
# _create_entry
# ===========================================================================


def test_create_entry_uses_host_as_title() -> None:
    flow = _make_flow()
    flow._host = "xenia.local"
    flow._create_entry("xenia.local")
    flow.async_create_entry.assert_called_once_with(
        title="xenia.local",
        data={"host": "xenia.local"},
    )


def test_create_entry_asserts_host_not_none() -> None:
    flow = _make_flow()
    flow._host = None
    with pytest.raises(AssertionError):
        flow._create_entry("any-title")


# ===========================================================================
# async_step_reconfigure
# ===========================================================================


@pytest.mark.asyncio
async def test_step_reconfigure_loads_existing_entry() -> None:
    flow = _make_flow()
    entry = MagicMock()
    entry.data = {"host": "old.host"}
    entry.title = "Old Machine"
    flow.context = {"entry_id": "abc123"}
    flow.hass.config_entries.async_get_entry = MagicMock(return_value=entry)

    with patch.object(
        flow, "async_step_reconfigure_confirm", new_callable=AsyncMock, return_value={}
    ):
        await flow.async_step_reconfigure()

    assert flow._host == "old.host"
    assert flow._entry is entry


@pytest.mark.asyncio
async def test_step_reconfigure_uses_default_host_if_not_in_data() -> None:
    flow = _make_flow()
    entry = MagicMock()
    entry.data = {}
    entry.title = "Machine"
    flow.context = {"entry_id": "abc123"}
    flow.hass.config_entries.async_get_entry = MagicMock(return_value=entry)

    with patch.object(
        flow, "async_step_reconfigure_confirm", new_callable=AsyncMock, return_value={}
    ):
        await flow.async_step_reconfigure()

    assert flow._host == DEFAULT_HOST


@pytest.mark.asyncio
async def test_step_reconfigure_asserts_entry_not_none() -> None:
    flow = _make_flow()
    flow.context = {"entry_id": "missing"}
    flow.hass.config_entries.async_get_entry = MagicMock(return_value=None)

    with pytest.raises(AssertionError):
        await flow.async_step_reconfigure()


# ===========================================================================
# async_step_reconfigure_confirm
# ===========================================================================


@pytest.mark.asyncio
async def test_reconfigure_confirm_shows_form_when_no_input() -> None:
    flow = _make_flow()
    flow._host = "xenia.local"
    flow._name = "My Machine"
    await flow.async_step_reconfigure_confirm(user_input=None)
    flow.async_show_form.assert_called_once()
    assert flow.async_show_form.call_args[1]["step_id"] == "reconfigure_confirm"


@pytest.mark.asyncio
async def test_reconfigure_confirm_aborts_on_success() -> None:
    flow = _make_flow()
    flow._host = "xenia.local"
    flow._name = "My Machine"
    flow._entry = MagicMock()
    flow._entry.entry_id = "abc123"
    flow.hass.config_entries.async_update_entry = MagicMock()
    flow.hass.config_entries.async_reload = AsyncMock()

    with patch.object(
        flow, "_async_test_connection", new_callable=AsyncMock, return_value=None
    ):
        await flow.async_step_reconfigure_confirm(user_input={"host": " new.host "})

    flow.async_abort.assert_called_once_with(reason="reconfigure_successful")


@pytest.mark.asyncio
async def test_reconfigure_confirm_strips_whitespace_from_host() -> None:
    flow = _make_flow()
    flow._host = "xenia.local"
    flow._name = "My Machine"
    flow._entry = MagicMock()
    flow._entry.entry_id = "abc123"
    flow.hass.config_entries.async_update_entry = MagicMock()
    flow.hass.config_entries.async_reload = AsyncMock()

    with patch.object(
        flow, "_async_test_connection", new_callable=AsyncMock, return_value=None
    ) as mock_test:
        await flow.async_step_reconfigure_confirm(user_input={"host": "  new.host  "})

    # The stripped host should be passed to the test function
    mock_test.assert_called_once_with(flow.hass, "new.host")


@pytest.mark.asyncio
async def test_reconfigure_confirm_shows_error_on_connection_failure() -> None:
    flow = _make_flow()
    flow._host = "xenia.local"
    flow._name = "My Machine"

    with patch.object(
        flow,
        "_async_test_connection",
        new_callable=AsyncMock,
        return_value="cannot_connect",
    ):
        await flow.async_step_reconfigure_confirm(user_input={"host": "bad.host"})

    flow.async_show_form.assert_called_once()
    errors = flow.async_show_form.call_args[1]["errors"]
    assert errors.get("base") == "cannot_connect"


@pytest.mark.asyncio
async def test_reconfigure_confirm_does_not_abort_on_failure() -> None:
    flow = _make_flow()
    flow._host = "xenia.local"
    flow._name = "My Machine"

    with patch.object(
        flow,
        "_async_test_connection",
        new_callable=AsyncMock,
        return_value="cannot_connect",
    ):
        await flow.async_step_reconfigure_confirm(user_input={"host": "bad.host"})

    flow.async_abort.assert_not_called()


@pytest.mark.asyncio
async def test_reconfigure_confirm_asserts_host_not_none() -> None:
    flow = _make_flow()
    flow._host = None

    with pytest.raises(AssertionError):
        await flow.async_step_reconfigure_confirm(user_input=None)


# ===========================================================================
# _update_entry
# ===========================================================================


@pytest.mark.asyncio
async def test_update_entry_calls_update_and_reload() -> None:
    flow = _make_flow()
    flow._host = "new.host"
    flow._entry = MagicMock()
    flow._entry.entry_id = "abc123"
    flow.hass.config_entries.async_update_entry = MagicMock()
    flow.hass.config_entries.async_reload = AsyncMock()

    await flow._update_entry()

    flow.hass.config_entries.async_update_entry.assert_called_once()
    flow.hass.config_entries.async_reload.assert_called_once_with("abc123")


@pytest.mark.asyncio
async def test_update_entry_asserts_entry_not_none() -> None:
    flow = _make_flow()
    flow._host = "new.host"
    flow._entry = None

    with pytest.raises(AssertionError):
        await flow._update_entry()


@pytest.mark.asyncio
async def test_update_entry_asserts_host_not_none() -> None:
    flow = _make_flow()
    flow._host = None
    flow._entry = MagicMock()

    with pytest.raises(AssertionError):
        await flow._update_entry()


@pytest.mark.asyncio
async def test_update_entry_stores_correct_host_in_data() -> None:
    flow = _make_flow()
    flow._host = "final.host"
    flow._entry = MagicMock()
    flow._entry.entry_id = "abc123"
    flow.hass.config_entries.async_update_entry = MagicMock()
    flow.hass.config_entries.async_reload = AsyncMock()

    await flow._update_entry()

    call_kwargs = flow.hass.config_entries.async_update_entry.call_args[1]
    assert call_kwargs["data"]["host"] == "final.host"


# ===========================================================================
# XeniaOptionsFlow — helpers
# ===========================================================================


def _make_options_flow(
    current_options: dict | None = None,
) -> XeniaOptionsFlow:
    """Build a XeniaOptionsFlow with mocked internals."""
    flow = XeniaOptionsFlow()
    flow.hass = _make_hass()

    # OptionsFlow.config_entry is a property that looks up the entry via handler
    mock_entry = MagicMock()
    mock_entry.data = {"host": "xenia.local"}
    mock_entry.options = current_options or {}
    mock_entry.domain = XENIA_DOMAIN
    flow.handler = "test_entry_id"
    flow.hass.config_entries.async_get_known_entry = MagicMock(return_value=mock_entry)

    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
    flow.async_show_form = MagicMock(return_value={"type": "form"})
    flow.async_abort = MagicMock(return_value={"type": "abort"})
    return flow


# ===========================================================================
# XeniaOptionsFlow — async_step_init
# ===========================================================================


@pytest.mark.asyncio
async def test_options_init_shows_form_when_no_input() -> None:
    flow = _make_options_flow()
    await flow.async_step_init(user_input=None)
    flow.async_show_form.assert_called_once()
    assert flow.async_show_form.call_args[1]["step_id"] == "init"


@pytest.mark.asyncio
async def test_options_init_disabling_creates_entry_with_disabled() -> None:
    flow = _make_options_flow(
        current_options={
            CONF_WEIGHT_MANAGEMENT_ENABLED: True,
            CONF_MANAGED_SCRIPT_ID: 17,
        }
    )
    await flow.async_step_init(user_input={CONF_WEIGHT_MANAGEMENT_ENABLED: False})
    flow.async_create_entry.assert_called_once()
    entry_data = flow.async_create_entry.call_args[1]["data"]
    assert entry_data[CONF_WEIGHT_MANAGEMENT_ENABLED] is False
    assert entry_data[CONF_MANAGED_SCRIPT_ID] is None


@pytest.mark.asyncio
async def test_options_init_enabling_proceeds_to_script_selection() -> None:
    flow = _make_options_flow()
    # When enabling, it should call async_step_select_script (which shows a form)
    with patch.object(
        flow,
        "async_step_select_script",
        new_callable=AsyncMock,
        return_value={"type": "form"},
    ) as mock_select:
        await flow.async_step_init(user_input={CONF_WEIGHT_MANAGEMENT_ENABLED: True})
    mock_select.assert_called_once()


# ===========================================================================
# XeniaOptionsFlow — async_step_select_script
# ===========================================================================


@pytest.mark.asyncio
async def test_options_select_script_shows_scripts_with_weight_command() -> None:
    flow = _make_options_flow()
    mock_xenia = MagicMock()
    mock_xenia.get_scripts = AsyncMock(return_value={10: "WithWeight", 20: "NoWeight"})
    # Script 10 has weight command, script 20 does not
    mock_xenia.read_script = AsyncMock(
        side_effect=lambda sid: (
            {"Content": "1;13;27 45;7;", "Title": "WithWeight"}
            if sid == 10
            else {"Content": "1;13;7;", "Title": "NoWeight"}
        )
    )
    with (
        patch(
            "custom_components.xenia_home.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.xenia_home.config_flow.Xenia",
            return_value=mock_xenia,
        ),
    ):
        await flow.async_step_select_script(user_input=None)

    flow.async_show_form.assert_called_once()
    assert flow.async_show_form.call_args[1]["step_id"] == "select_script"


@pytest.mark.asyncio
async def test_options_select_script_proceeds_to_configure_weight() -> None:
    flow = _make_options_flow()
    await flow.async_step_select_script(user_input={CONF_MANAGED_SCRIPT_ID: "17"})
    # Should store the script id and show the configure_weight form
    assert flow._managed_script_id == 17
    flow.async_show_form.assert_called_once()
    assert flow.async_show_form.call_args[1]["step_id"] == "configure_weight"


@pytest.mark.asyncio
async def test_options_select_script_create_new_calls_api() -> None:
    flow = _make_options_flow()
    mock_xenia = MagicMock()
    mock_xenia.create_script = AsyncMock()
    mock_xenia.get_scripts = AsyncMock(return_value={25: DEFAULT_SCRIPT_NAME})
    with (
        patch(
            "custom_components.xenia_home.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.xenia_home.config_flow.Xenia",
            return_value=mock_xenia,
        ),
    ):
        await flow.async_step_select_script(
            user_input={CONF_MANAGED_SCRIPT_ID: CREATE_NEW_SCRIPT}
        )

    mock_xenia.create_script.assert_called_once()
    # Should proceed to configure_weight step instead of creating entry directly
    assert flow._managed_script_id == 25
    flow.async_show_form.assert_called_once()
    assert flow.async_show_form.call_args[1]["step_id"] == "configure_weight"


@pytest.mark.asyncio
async def test_options_select_script_aborts_on_connection_error() -> None:
    flow = _make_options_flow()
    mock_xenia = MagicMock()
    mock_xenia.get_scripts = AsyncMock(side_effect=OSError("connection refused"))
    with (
        patch(
            "custom_components.xenia_home.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.xenia_home.config_flow.Xenia",
            return_value=mock_xenia,
        ),
    ):
        await flow.async_step_select_script(user_input=None)

    flow.async_abort.assert_called_once_with(reason="cannot_connect")


@pytest.mark.asyncio
async def test_options_create_new_aborts_when_script_not_found() -> None:
    """If the newly created script cannot be found by name, abort."""
    flow = _make_options_flow()
    mock_xenia = MagicMock()
    mock_xenia.create_script = AsyncMock()
    # Script list doesn't contain the expected name
    mock_xenia.get_scripts = AsyncMock(return_value={10: "SomeOtherScript"})
    with (
        patch(
            "custom_components.xenia_home.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.xenia_home.config_flow.Xenia",
            return_value=mock_xenia,
        ),
    ):
        await flow.async_step_select_script(
            user_input={CONF_MANAGED_SCRIPT_ID: CREATE_NEW_SCRIPT}
        )

    flow.async_abort.assert_called_once_with(reason="cannot_connect")


@pytest.mark.asyncio
async def test_options_create_new_aborts_on_api_error() -> None:
    flow = _make_options_flow()
    mock_xenia = MagicMock()
    mock_xenia.create_script = AsyncMock(side_effect=TimeoutError("timeout"))
    with (
        patch(
            "custom_components.xenia_home.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.xenia_home.config_flow.Xenia",
            return_value=mock_xenia,
        ),
    ):
        await flow.async_step_select_script(
            user_input={CONF_MANAGED_SCRIPT_ID: CREATE_NEW_SCRIPT}
        )

    flow.async_abort.assert_called_once_with(reason="cannot_connect")


# ===========================================================================
# XeniaOptionsFlow — async_step_configure_weight
# ===========================================================================


@pytest.mark.asyncio
async def test_options_configure_weight_shows_form_when_no_input() -> None:
    flow = _make_options_flow()
    flow._managed_script_id = 17
    await flow.async_step_configure_weight(user_input=None)
    flow.async_show_form.assert_called_once()
    assert flow.async_show_form.call_args[1]["step_id"] == "configure_weight"


@pytest.mark.asyncio
async def test_options_configure_weight_uses_defaults_for_new_setup() -> None:
    flow = _make_options_flow()
    flow._managed_script_id = 17
    await flow.async_step_configure_weight(user_input=None)
    schema = flow.async_show_form.call_args[1]["data_schema"]
    # Check defaults are set in schema
    schema_dict = schema.schema
    for key, validator in schema_dict.items():
        if key == CONF_WEIGHT_MIN:
            assert key.default() == DEFAULT_WEIGHT_MIN
        elif key == CONF_WEIGHT_MAX:
            assert key.default() == DEFAULT_WEIGHT_MAX
        elif key == CONF_WEIGHT_STEP:
            assert key.default() == DEFAULT_WEIGHT_STEP


@pytest.mark.asyncio
async def test_options_configure_weight_pre_populates_from_existing_options() -> None:
    flow = _make_options_flow(
        current_options={
            CONF_WEIGHT_MANAGEMENT_ENABLED: True,
            CONF_MANAGED_SCRIPT_ID: 17,
            CONF_WEIGHT_MIN: 10.0,
            CONF_WEIGHT_MAX: 60.0,
            CONF_WEIGHT_STEP: 0.1,
        }
    )
    flow._managed_script_id = 17
    await flow.async_step_configure_weight(user_input=None)
    schema = flow.async_show_form.call_args[1]["data_schema"]
    schema_dict = schema.schema
    for key, validator in schema_dict.items():
        if key == CONF_WEIGHT_MIN:
            assert key.default() == 10.0
        elif key == CONF_WEIGHT_MAX:
            assert key.default() == 60.0
        elif key == CONF_WEIGHT_STEP:
            assert key.default() == 0.1


@pytest.mark.asyncio
async def test_options_configure_weight_creates_entry_with_all_values() -> None:
    flow = _make_options_flow()
    flow._managed_script_id = 17
    await flow.async_step_configure_weight(
        user_input={
            CONF_WEIGHT_MIN: 20.0,
            CONF_WEIGHT_MAX: 45.0,
            CONF_WEIGHT_STEP: 0.1,
        }
    )
    flow.async_create_entry.assert_called_once()
    entry_data = flow.async_create_entry.call_args[1]["data"]
    assert entry_data[CONF_WEIGHT_MANAGEMENT_ENABLED] is True
    assert entry_data[CONF_MANAGED_SCRIPT_ID] == 17
    assert entry_data[CONF_WEIGHT_MIN] == 20.0
    assert entry_data[CONF_WEIGHT_MAX] == 45.0
    assert entry_data[CONF_WEIGHT_STEP] == 0.1


@pytest.mark.asyncio
async def test_options_full_flow_init_to_configure_weight() -> None:
    """End-to-end: enable weight → select script → configure weight → entry."""
    flow = _make_options_flow()
    mock_xenia = MagicMock()
    mock_xenia.get_scripts = AsyncMock(return_value={10: "Shot"})
    mock_xenia.read_script = AsyncMock(
        return_value={"Content": "1;13;27 45;7;", "Title": "Shot"}
    )
    with (
        patch(
            "custom_components.xenia_home.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.xenia_home.config_flow.Xenia",
            return_value=mock_xenia,
        ),
    ):
        # Step 1: enable weight management
        await flow.async_step_init(user_input={CONF_WEIGHT_MANAGEMENT_ENABLED: True})
        # Step 2: select a script (shows configure_weight form)
        await flow.async_step_select_script(user_input={CONF_MANAGED_SCRIPT_ID: "10"})
    # Step 3: configure weight
    await flow.async_step_configure_weight(
        user_input={
            CONF_WEIGHT_MIN: 25.0,
            CONF_WEIGHT_MAX: 50.0,
            CONF_WEIGHT_STEP: 0.5,
        }
    )
    flow.async_create_entry.assert_called_once()
    entry_data = flow.async_create_entry.call_args[1]["data"]
    assert entry_data[CONF_MANAGED_SCRIPT_ID] == 10
    assert entry_data[CONF_WEIGHT_MIN] == 25.0
