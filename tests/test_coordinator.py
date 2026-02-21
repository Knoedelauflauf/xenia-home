"""Unit tests for coordinator.py — XeniaDataUpdateCoordinator and XeniaConfigCoordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.xenia_home.coordinator import (
    BUILTIN_SCRIPTS,
    XeniaConfigCoordinator,
    XeniaConfigData,
    XeniaCoordinatorData,
    XeniaDataUpdateCoordinator,
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


def _make_hass() -> MagicMock:
    hass = MagicMock()
    hass.loop = MagicMock()
    hass.bus = MagicMock()
    hass.config = MagicMock()
    hass.config.time_zone = "UTC"
    return hass


def _make_config_entry(entry_id: str = "test_entry") -> MagicMock:
    entry = MagicMock()
    entry.entry_id = entry_id
    return entry


def _make_xenia_mock() -> MagicMock:
    xenia = MagicMock()
    xenia.get_overview = AsyncMock(
        return_value=XeniaOverviewData.from_dict({"MA_STATUS": 1})
    )
    xenia.get_overview_single = AsyncMock(
        return_value=XeniaOverviewSingleData.from_dict({})
    )
    xenia.get_machine = AsyncMock(
        return_value=XeniaMachineData.from_dict({"MA_TYPE": 1})
    )
    xenia.get_scripts = AsyncMock(return_value={10: "MyShot"})
    xenia.get_switches = AsyncMock(return_value={"SWITCH_SET_LEFT_LEFT_0": 1})
    return xenia


# ===========================================================================
# BUILTIN_SCRIPTS
# ===========================================================================


def test_builtin_scripts_contains_none_entry() -> None:
    assert 0 in BUILTIN_SCRIPTS
    assert BUILTIN_SCRIPTS[0] == "None"


def test_builtin_scripts_contains_espresso() -> None:
    assert 1 in BUILTIN_SCRIPTS
    assert BUILTIN_SCRIPTS[1] == "Espresso"


def test_builtin_scripts_contains_espresso_endless() -> None:
    assert 2 in BUILTIN_SCRIPTS
    assert BUILTIN_SCRIPTS[2] == "Espresso endless"


# ===========================================================================
# XeniaCoordinatorData
# ===========================================================================


def test_coordinator_data_stores_overview_and_single(
    overview_data: XeniaOverviewData,
    overview_single_data: XeniaOverviewSingleData,
) -> None:
    data = XeniaCoordinatorData(overview=overview_data, overview_single=overview_single_data)
    assert data.overview is overview_data
    assert data.overview_single is overview_single_data


# ===========================================================================
# XeniaConfigData
# ===========================================================================


def test_config_data_default_scripts_is_empty(machine_data: XeniaMachineData) -> None:
    data = XeniaConfigData(machine=machine_data)
    assert data.scripts == {}


def test_config_data_default_switches_is_empty(machine_data: XeniaMachineData) -> None:
    data = XeniaConfigData(machine=machine_data)
    assert data.switches == {}


def test_config_data_stores_machine(machine_data: XeniaMachineData) -> None:
    data = XeniaConfigData(machine=machine_data)
    assert data.machine is machine_data


# ===========================================================================
# XeniaRuntimeData
# ===========================================================================


def test_runtime_data_stores_both_coordinators() -> None:
    coord = MagicMock()
    config_coord = MagicMock()
    runtime = XeniaRuntimeData(coordinator=coord, config_coordinator=config_coord)
    assert runtime.coordinator is coord
    assert runtime.config_coordinator is config_coord


# ===========================================================================
# XeniaDataUpdateCoordinator.__init__
# ===========================================================================


def test_data_update_coordinator_initializes_with_empty_data() -> None:
    hass = _make_hass()
    entry = _make_config_entry()
    xenia = _make_xenia_mock()

    with patch(
        "custom_components.xenia_home.coordinator.DataUpdateCoordinator.__init__",
        return_value=None,
    ):
        coordinator = XeniaDataUpdateCoordinator.__new__(XeniaDataUpdateCoordinator)
        coordinator.hass = hass
        coordinator.config_entry = entry
        coordinator.logger = MagicMock()
        # Call real __init__ indirectly through attribute assignment
        coordinator.xenia = xenia

    # The default data should be XeniaCoordinatorData with zero values
    assert xenia is coordinator.xenia


def test_data_update_coordinator_stores_xenia_client() -> None:
    hass = _make_hass()
    entry = _make_config_entry()
    xenia = _make_xenia_mock()

    with patch("homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"):
        coordinator = XeniaDataUpdateCoordinator(hass, entry, xenia)

    assert coordinator.xenia is xenia


# ===========================================================================
# XeniaDataUpdateCoordinator._async_update_data
# ===========================================================================


@pytest.mark.asyncio
async def test_data_coordinator_update_returns_coordinator_data() -> None:
    hass = _make_hass()
    entry = _make_config_entry()
    xenia = _make_xenia_mock()

    with patch("homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"):
        coordinator = XeniaDataUpdateCoordinator(hass, entry, xenia)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await coordinator._async_update_data()

    assert isinstance(result, XeniaCoordinatorData)
    assert result.overview.ma_status.value == 1


@pytest.mark.asyncio
async def test_data_coordinator_update_calls_both_endpoints() -> None:
    hass = _make_hass()
    entry = _make_config_entry()
    xenia = _make_xenia_mock()

    with patch("homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"):
        coordinator = XeniaDataUpdateCoordinator(hass, entry, xenia)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await coordinator._async_update_data()

    xenia.get_overview.assert_called_once()
    xenia.get_overview_single.assert_called_once()


@pytest.mark.asyncio
async def test_data_coordinator_update_raises_update_failed_on_exception() -> None:
    hass = _make_hass()
    entry = _make_config_entry()
    xenia = _make_xenia_mock()
    xenia.get_overview = AsyncMock(side_effect=OSError("network error"))

    with patch("homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"):
        coordinator = XeniaDataUpdateCoordinator(hass, entry, xenia)

    with pytest.raises(UpdateFailed, match="Xenia fetch failed"):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_data_coordinator_update_raises_update_failed_on_single_exception() -> None:
    hass = _make_hass()
    entry = _make_config_entry()
    xenia = _make_xenia_mock()
    xenia.get_overview_single = AsyncMock(side_effect=TimeoutError("timeout"))

    with patch("homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"):
        coordinator = XeniaDataUpdateCoordinator(hass, entry, xenia)

    with pytest.raises(UpdateFailed, match="Xenia fetch failed"):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await coordinator._async_update_data()


# ===========================================================================
# XeniaConfigCoordinator.__init__
# ===========================================================================


def test_config_coordinator_stores_xenia_client() -> None:
    hass = _make_hass()
    entry = _make_config_entry()
    xenia = _make_xenia_mock()

    with patch("homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"):
        coordinator = XeniaConfigCoordinator(hass, entry, xenia)

    assert coordinator.xenia is xenia


def test_config_coordinator_selected_script_id_starts_none() -> None:
    hass = _make_hass()
    entry = _make_config_entry()
    xenia = _make_xenia_mock()

    with patch("homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"):
        coordinator = XeniaConfigCoordinator(hass, entry, xenia)

    assert coordinator.selected_script_id is None


# ===========================================================================
# XeniaConfigCoordinator._async_update_data
# ===========================================================================


@pytest.mark.asyncio
async def test_config_coordinator_update_returns_config_data() -> None:
    hass = _make_hass()
    entry = _make_config_entry()
    xenia = _make_xenia_mock()

    with patch("homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"):
        coordinator = XeniaConfigCoordinator(hass, entry, xenia)

    result = await coordinator._async_update_data()

    assert isinstance(result, XeniaConfigData)
    assert result.machine is not None


@pytest.mark.asyncio
async def test_config_coordinator_update_merges_builtin_scripts() -> None:
    hass = _make_hass()
    entry = _make_config_entry()
    xenia = _make_xenia_mock()
    xenia.get_scripts = AsyncMock(return_value={10: "MyShot"})

    with patch("homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"):
        coordinator = XeniaConfigCoordinator(hass, entry, xenia)

    result = await coordinator._async_update_data()

    # Built-in scripts should be included
    assert 0 in result.scripts
    assert 1 in result.scripts
    assert 2 in result.scripts
    # User scripts should also be present
    assert 10 in result.scripts
    assert result.scripts[10] == "MyShot"


@pytest.mark.asyncio
async def test_config_coordinator_update_user_scripts_override_builtin() -> None:
    """If a user script has the same ID as a built-in, user script wins."""
    hass = _make_hass()
    entry = _make_config_entry()
    xenia = _make_xenia_mock()
    xenia.get_scripts = AsyncMock(return_value={1: "Custom Espresso"})

    with patch("homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"):
        coordinator = XeniaConfigCoordinator(hass, entry, xenia)

    result = await coordinator._async_update_data()
    assert result.scripts[1] == "Custom Espresso"


@pytest.mark.asyncio
async def test_config_coordinator_update_stores_switches() -> None:
    hass = _make_hass()
    entry = _make_config_entry()
    xenia = _make_xenia_mock()

    with patch("homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"):
        coordinator = XeniaConfigCoordinator(hass, entry, xenia)

    result = await coordinator._async_update_data()
    assert result.switches == {"SWITCH_SET_LEFT_LEFT_0": 1}


@pytest.mark.asyncio
async def test_config_coordinator_update_raises_update_failed_on_machine_error() -> None:
    hass = _make_hass()
    entry = _make_config_entry()
    xenia = _make_xenia_mock()
    xenia.get_machine = AsyncMock(side_effect=OSError("unreachable"))

    with patch("homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"):
        coordinator = XeniaConfigCoordinator(hass, entry, xenia)

    with pytest.raises(UpdateFailed, match="Xenia config fetch failed"):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_config_coordinator_update_raises_update_failed_on_scripts_error() -> None:
    hass = _make_hass()
    entry = _make_config_entry()
    xenia = _make_xenia_mock()
    xenia.get_scripts = AsyncMock(side_effect=TimeoutError("timeout"))

    with patch("homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"):
        coordinator = XeniaConfigCoordinator(hass, entry, xenia)

    with pytest.raises(UpdateFailed, match="Xenia config fetch failed"):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_config_coordinator_update_raises_update_failed_on_switches_error() -> None:
    hass = _make_hass()
    entry = _make_config_entry()
    xenia = _make_xenia_mock()
    xenia.get_switches = AsyncMock(side_effect=ConnectionError("refused"))

    with patch("homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"):
        coordinator = XeniaConfigCoordinator(hass, entry, xenia)

    with pytest.raises(UpdateFailed, match="Xenia config fetch failed"):
        await coordinator._async_update_data()
