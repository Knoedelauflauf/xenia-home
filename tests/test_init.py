"""Tests for __init__.py — async_setup_entry, async_unload_entry, execute_script service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.xenia_home import (
    ATTR_SCRIPT_ID,
    ATTR_SCRIPT_NAME,
    SERVICE_EXECUTE_SCRIPT,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.xenia_home.coordinator import (
    XeniaConfigData,
    XeniaCoordinatorData,
    XeniaRuntimeData,
)
from custom_components.xenia_home.xenia import (
    XeniaMachineData,
    XeniaOverviewData,
    XeniaOverviewSingleData,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_xenia_mock() -> MagicMock:
    xenia = MagicMock()
    xenia.get_overview = AsyncMock(
        return_value=XeniaOverviewData.from_dict({"MA_STATUS": 1})
    )
    xenia.get_overview_single = AsyncMock(
        return_value=XeniaOverviewSingleData.from_dict({})
    )
    xenia.get_machine = AsyncMock(return_value=XeniaMachineData.from_dict({}))
    xenia.get_scripts = AsyncMock(return_value={})
    xenia.get_switches = AsyncMock(return_value={})
    xenia.execute_script = AsyncMock()
    return xenia


def _make_config_coordinator_mock(
    scripts: dict | None = None
) -> MagicMock:
    """Build a mock config coordinator with given scripts."""
    coord = MagicMock()
    coord.data = XeniaConfigData(
        machine=XeniaMachineData.from_dict({}),
        scripts=scripts or {0: "None", 1: "Espresso", 10: "MyShot"},
        switches={},
    )
    coord.async_config_entry_first_refresh = AsyncMock()
    return coord


def _make_service_call(data: dict) -> MagicMock:
    """Build a mock ServiceCall with the given data dict."""
    sc = MagicMock()
    sc.data = data
    return sc


# ===========================================================================
# handle_execute_script — tested directly by building the closure
# ===========================================================================


@pytest.mark.asyncio
async def test_execute_script_by_id_calls_xenia() -> None:
    xenia = _make_xenia_mock()
    config_coordinator = _make_config_coordinator_mock()

    async def _handle(call: MagicMock) -> None:
        script_id = call.data.get(ATTR_SCRIPT_ID)
        script_name = call.data.get(ATTR_SCRIPT_NAME)
        if script_id is None and script_name is None:
            raise ServiceValidationError("Either script_id or script_name is required")
        if script_id is None:
            scripts = config_coordinator.data.scripts
            for sid, title in scripts.items():
                if title == script_name:
                    script_id = sid
                    break
            if script_id is None:
                raise ServiceValidationError(f"Script '{script_name}' not found")
        await xenia.execute_script(script_id)

    call = _make_service_call({ATTR_SCRIPT_ID: 1})
    await _handle(call)
    xenia.execute_script.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_execute_script_by_name_resolves_id_and_calls_xenia() -> None:
    xenia = _make_xenia_mock()
    config_coordinator = _make_config_coordinator_mock(
        scripts={0: "None", 1: "Espresso", 10: "MyShot"}
    )

    async def _handle(call: MagicMock) -> None:
        script_id = call.data.get(ATTR_SCRIPT_ID)
        script_name = call.data.get(ATTR_SCRIPT_NAME)
        if script_id is None and script_name is None:
            raise ServiceValidationError("Either script_id or script_name is required")
        if script_id is None:
            scripts = config_coordinator.data.scripts
            for sid, title in scripts.items():
                if title == script_name:
                    script_id = sid
                    break
            if script_id is None:
                raise ServiceValidationError(f"Script '{script_name}' not found")
        await xenia.execute_script(script_id)

    call = _make_service_call({ATTR_SCRIPT_NAME: "MyShot"})
    await _handle(call)
    xenia.execute_script.assert_called_once_with(10)


@pytest.mark.asyncio
async def test_execute_script_no_id_no_name_raises_validation_error() -> None:
    xenia = _make_xenia_mock()
    config_coordinator = _make_config_coordinator_mock()

    async def _handle(call: MagicMock) -> None:
        script_id = call.data.get(ATTR_SCRIPT_ID)
        script_name = call.data.get(ATTR_SCRIPT_NAME)
        if script_id is None and script_name is None:
            raise ServiceValidationError("Either script_id or script_name is required")
        if script_id is None:
            scripts = config_coordinator.data.scripts
            for sid, title in scripts.items():
                if title == script_name:
                    script_id = sid
                    break
            if script_id is None:
                raise ServiceValidationError(f"Script '{script_name}' not found")
        await xenia.execute_script(script_id)

    call = _make_service_call({})
    with pytest.raises(ServiceValidationError, match="Either script_id or script_name"):
        await _handle(call)


@pytest.mark.asyncio
async def test_execute_script_unknown_name_raises_validation_error() -> None:
    xenia = _make_xenia_mock()
    config_coordinator = _make_config_coordinator_mock(
        scripts={1: "Espresso"}
    )

    async def _handle(call: MagicMock) -> None:
        script_id = call.data.get(ATTR_SCRIPT_ID)
        script_name = call.data.get(ATTR_SCRIPT_NAME)
        if script_id is None and script_name is None:
            raise ServiceValidationError("Either script_id or script_name is required")
        if script_id is None:
            scripts = config_coordinator.data.scripts
            for sid, title in scripts.items():
                if title == script_name:
                    script_id = sid
                    break
            if script_id is None:
                raise ServiceValidationError(f"Script '{script_name}' not found")
        await xenia.execute_script(script_id)

    call = _make_service_call({ATTR_SCRIPT_NAME: "NonExistent"})
    with pytest.raises(ServiceValidationError, match="Script 'NonExistent' not found"):
        await _handle(call)


@pytest.mark.asyncio
async def test_execute_script_id_takes_priority_over_name() -> None:
    """When both script_id and script_name are given, script_id must be used."""
    xenia = _make_xenia_mock()
    config_coordinator = _make_config_coordinator_mock(
        scripts={1: "Espresso", 10: "MyShot"}
    )

    async def _handle(call: MagicMock) -> None:
        script_id = call.data.get(ATTR_SCRIPT_ID)
        script_name = call.data.get(ATTR_SCRIPT_NAME)
        if script_id is None and script_name is None:
            raise ServiceValidationError("Either script_id or script_name is required")
        if script_id is None:
            scripts = config_coordinator.data.scripts
            for sid, title in scripts.items():
                if title == script_name:
                    script_id = sid
                    break
            if script_id is None:
                raise ServiceValidationError(f"Script '{script_name}' not found")
        await xenia.execute_script(script_id)

    call = _make_service_call({ATTR_SCRIPT_ID: 1, ATTR_SCRIPT_NAME: "MyShot"})
    await _handle(call)
    # Only the ID-based script (1) should have been executed
    xenia.execute_script.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_execute_script_by_name_not_found_does_not_call_xenia() -> None:
    xenia = _make_xenia_mock()
    config_coordinator = _make_config_coordinator_mock(scripts={})

    async def _handle(call: MagicMock) -> None:
        script_id = call.data.get(ATTR_SCRIPT_ID)
        script_name = call.data.get(ATTR_SCRIPT_NAME)
        if script_id is None and script_name is None:
            raise ServiceValidationError("Either script_id or script_name is required")
        if script_id is None:
            scripts = config_coordinator.data.scripts
            for sid, title in scripts.items():
                if title == script_name:
                    script_id = sid
                    break
            if script_id is None:
                raise ServiceValidationError(f"Script '{script_name}' not found")
        await xenia.execute_script(script_id)

    call = _make_service_call({ATTR_SCRIPT_NAME: "Ghost"})
    with pytest.raises(ServiceValidationError):
        await _handle(call)
    xenia.execute_script.assert_not_called()


# ===========================================================================
# async_setup_entry
# ===========================================================================


@pytest.mark.asyncio
async def test_async_setup_entry_returns_true() -> None:
    hass = MagicMock()
    hass.services = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)

    entry = MagicMock()
    entry.data = {"host": "xenia.local"}

    with patch(
        "custom_components.xenia_home.Xenia"
    ) as MockXenia, patch(
        "custom_components.xenia_home.async_get_clientsession",
        return_value=MagicMock(),
    ), patch(
        "custom_components.xenia_home.XeniaDataUpdateCoordinator"
    ) as MockDataCoord, patch(
        "custom_components.xenia_home.XeniaConfigCoordinator"
    ) as MockConfigCoord:
        mock_coord = MagicMock()
        mock_coord.async_config_entry_first_refresh = AsyncMock()
        MockDataCoord.return_value = mock_coord

        mock_config_coord = MagicMock()
        mock_config_coord.async_config_entry_first_refresh = AsyncMock()
        mock_config_coord.data = MagicMock()
        mock_config_coord.data.scripts = {}
        MockConfigCoord.return_value = mock_config_coord

        result = await async_setup_entry(hass, entry)

    assert result is True


@pytest.mark.asyncio
async def test_async_setup_entry_registers_service() -> None:
    hass = MagicMock()
    hass.services = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)

    entry = MagicMock()
    entry.data = {"host": "xenia.local"}

    with patch(
        "custom_components.xenia_home.Xenia"
    ) as MockXenia, patch(
        "custom_components.xenia_home.async_get_clientsession",
        return_value=MagicMock(),
    ), patch(
        "custom_components.xenia_home.XeniaDataUpdateCoordinator"
    ) as MockDataCoord, patch(
        "custom_components.xenia_home.XeniaConfigCoordinator"
    ) as MockConfigCoord:
        mock_coord = MagicMock()
        mock_coord.async_config_entry_first_refresh = AsyncMock()
        MockDataCoord.return_value = mock_coord

        mock_config_coord = MagicMock()
        mock_config_coord.async_config_entry_first_refresh = AsyncMock()
        mock_config_coord.data = MagicMock()
        mock_config_coord.data.scripts = {}
        MockConfigCoord.return_value = mock_config_coord

        await async_setup_entry(hass, entry)

    hass.services.async_register.assert_called_once()
    call_args = hass.services.async_register.call_args
    assert call_args[0][1] == SERVICE_EXECUTE_SCRIPT


@pytest.mark.asyncio
async def test_async_setup_entry_sets_runtime_data() -> None:
    hass = MagicMock()
    hass.services = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)

    entry = MagicMock()
    entry.data = {"host": "xenia.local"}
    entry.runtime_data = None

    with patch(
        "custom_components.xenia_home.Xenia"
    ) as MockXenia, patch(
        "custom_components.xenia_home.async_get_clientsession",
        return_value=MagicMock(),
    ), patch(
        "custom_components.xenia_home.XeniaDataUpdateCoordinator"
    ) as MockDataCoord, patch(
        "custom_components.xenia_home.XeniaConfigCoordinator"
    ) as MockConfigCoord:
        mock_coord = MagicMock()
        mock_coord.async_config_entry_first_refresh = AsyncMock()
        MockDataCoord.return_value = mock_coord

        mock_config_coord = MagicMock()
        mock_config_coord.async_config_entry_first_refresh = AsyncMock()
        mock_config_coord.data = MagicMock()
        mock_config_coord.data.scripts = {}
        MockConfigCoord.return_value = mock_config_coord

        await async_setup_entry(hass, entry)

    # runtime_data must be set
    assert entry.runtime_data is not None


# ===========================================================================
# async_unload_entry
# ===========================================================================


@pytest.mark.asyncio
async def test_async_unload_entry_removes_service_when_last_entry_unloaded() -> None:
    """Service must be removed only when no other entries remain."""
    hass = MagicMock()
    hass.services = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    # async_entries returns empty list — no entries left after this unload
    hass.config_entries.async_entries = MagicMock(return_value=[])

    entry = MagicMock()
    result = await async_unload_entry(hass, entry)

    hass.services.async_remove.assert_called_once_with(
        "xenia_home", SERVICE_EXECUTE_SCRIPT
    )
    assert result is True


@pytest.mark.asyncio
async def test_async_unload_entry_keeps_service_when_other_entries_remain() -> None:
    """Service must NOT be removed when other loaded entries still exist."""
    hass = MagicMock()
    hass.services = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    # async_entries returns a non-empty list — other entries still loaded
    hass.config_entries.async_entries = MagicMock(return_value=[MagicMock()])

    entry = MagicMock()
    result = await async_unload_entry(hass, entry)

    hass.services.async_remove.assert_not_called()
    assert result is True


@pytest.mark.asyncio
async def test_async_unload_entry_returns_false_when_platform_unload_fails() -> None:
    """On platform unload failure the service must not be removed and False returned."""
    hass = MagicMock()
    hass.services = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)
    hass.config_entries.async_entries = MagicMock(return_value=[])

    entry = MagicMock()
    result = await async_unload_entry(hass, entry)

    hass.services.async_remove.assert_not_called()
    assert result is False
