"""Tests for config_flow.py — XeniaConfigFlow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.xenia_home.config_flow import XeniaConfigFlow
from custom_components.xenia_home.const import DEFAULT_HOST, XENIA_DOMAIN


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
    with patch(
        "custom_components.xenia_home.config_flow.Xenia"
    ) as mock_xenia_cls, patch(
        "custom_components.xenia_home.config_flow.async_get_clientsession",
        return_value=MagicMock(),
    ), patch(
        "asyncio.wait_for", new_callable=AsyncMock, return_value=True
    ):
        result = await flow._async_test_connection(flow.hass, "xenia.local")

    assert result is None


@pytest.mark.asyncio
async def test_async_test_connection_returns_cannot_connect_when_not_connected() -> None:
    flow = _make_flow()
    with patch(
        "custom_components.xenia_home.config_flow.Xenia"
    ) as mock_xenia_cls, patch(
        "custom_components.xenia_home.config_flow.async_get_clientsession",
        return_value=MagicMock(),
    ), patch(
        "asyncio.wait_for", new_callable=AsyncMock, return_value=False
    ):
        result = await flow._async_test_connection(flow.hass, "xenia.local")

    assert result == "cannot_connect"


@pytest.mark.asyncio
async def test_async_test_connection_returns_cannot_connect_on_timeout() -> None:
    flow = _make_flow()
    with patch(
        "custom_components.xenia_home.config_flow.Xenia"
    ) as mock_xenia_cls, patch(
        "custom_components.xenia_home.config_flow.async_get_clientsession",
        return_value=MagicMock(),
    ), patch(
        "asyncio.wait_for",
        new_callable=AsyncMock,
        side_effect=TimeoutError("timeout"),
    ):
        result = await flow._async_test_connection(flow.hass, "xenia.local")

    assert result == "cannot_connect"


@pytest.mark.asyncio
async def test_async_test_connection_returns_cannot_connect_on_os_error() -> None:
    flow = _make_flow()
    with patch(
        "custom_components.xenia_home.config_flow.Xenia"
    ) as mock_xenia_cls, patch(
        "custom_components.xenia_home.config_flow.async_get_clientsession",
        return_value=MagicMock(),
    ), patch(
        "asyncio.wait_for",
        new_callable=AsyncMock,
        side_effect=OSError("connection refused"),
    ):
        result = await flow._async_test_connection(flow.hass, "xenia.local")

    assert result == "cannot_connect"


@pytest.mark.asyncio
async def test_async_test_connection_returns_cannot_connect_on_client_error() -> None:
    from aiohttp import ClientError

    flow = _make_flow()
    with patch(
        "custom_components.xenia_home.config_flow.Xenia"
    ) as mock_xenia_cls, patch(
        "custom_components.xenia_home.config_flow.async_get_clientsession",
        return_value=MagicMock(),
    ), patch(
        "asyncio.wait_for",
        new_callable=AsyncMock,
        side_effect=ClientError("client error"),
    ):
        result = await flow._async_test_connection(flow.hass, "xenia.local")

    assert result == "cannot_connect"


# ===========================================================================
# async_step_user — no input (initial display)
# ===========================================================================


@pytest.mark.asyncio
async def test_step_user_shows_form_when_no_input() -> None:
    flow = _make_flow()
    result = await flow.async_step_user(user_input=None)
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
        result = await flow.async_step_user(user_input={"host": "xenia.local"})

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
        result = await flow.async_step_user(user_input={"host": "bad.host"})

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
    result = await flow.async_step_reconfigure_confirm(user_input=None)
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
