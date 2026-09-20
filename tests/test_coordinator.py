"""Tests for coordinator.py — fast and config coordinators."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.helpers.update_coordinator import UpdateFailed
import pytest

from custom_components.xenia_home.const import (
    POLL_INTERVAL_BREWING,
    POLL_INTERVAL_HEATING,
    POLL_INTERVAL_IDLE,
    POLL_INTERVAL_READY,
)
from custom_components.xenia_home.coordinator import (
    BUILTIN_SCRIPTS,
    XeniaConfigCoordinator,
    XeniaConfigData,
    XeniaCoordinatorData,
    XeniaDataUpdateCoordinator,
    XeniaRuntimeData,
)
from custom_components.xenia_home.xenia import (
    MachineStatus,
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
    return hass


def _make_entry(**options) -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.options = options
    return entry


def _make_xenia_mock(
    overview: dict | None = None,
    overview_single: dict | None = None,
) -> MagicMock:
    xenia = MagicMock()
    xenia.get_overview = AsyncMock(
        return_value=XeniaOverviewData.from_dict(overview or {"MA_STATUS": 1})
    )
    xenia.get_overview_single = AsyncMock(
        return_value=XeniaOverviewSingleData.from_dict(overview_single or {})
    )
    xenia.get_machine = AsyncMock(
        return_value=XeniaMachineData.from_dict({"MA_TYPE": 1})
    )
    xenia.get_scripts = AsyncMock(return_value={10: "MyShot"})
    xenia.get_switches = AsyncMock(return_value={"SWITCH_SET_LEFT_LEFT_0": 1})
    return xenia


def _make_data_coordinator(xenia=None, **options):
    """Build a fully constructed XeniaDataUpdateCoordinator with patched super."""
    hass = _make_hass()
    entry = _make_entry(**options)
    if xenia is None:
        xenia = _make_xenia_mock()
    with patch(
        "homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"
    ):
        coordinator = XeniaDataUpdateCoordinator(hass, entry, xenia)
        coordinator.config_entry = entry
        coordinator.data = None
    return coordinator


def _make_config_coordinator(xenia=None, **options):
    hass = _make_hass()
    entry = _make_entry(**options)
    if xenia is None:
        xenia = _make_xenia_mock()
    with patch(
        "homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"
    ):
        coordinator = XeniaConfigCoordinator(hass, entry, xenia)
        coordinator.config_entry = entry
    return coordinator


# ===========================================================================
# BUILTIN_SCRIPTS
# ===========================================================================


def test_builtin_scripts_has_three_entries() -> None:
    assert BUILTIN_SCRIPTS == {
        0: "None",
        1: "Espresso",
        2: "Espresso endless",
    }


# ===========================================================================
# Data classes
# ===========================================================================


def test_coordinator_data_holds_both_payloads() -> None:
    overview = XeniaOverviewData.from_dict({})
    single = XeniaOverviewSingleData.from_dict({})
    data = XeniaCoordinatorData(overview=overview, overview_single=single)
    assert data.overview is overview
    assert data.overview_single is single


def test_config_data_defaults_are_empty() -> None:
    machine = XeniaMachineData.from_dict({})
    data = XeniaConfigData(machine=machine)
    assert data.scripts == {}
    assert data.switches == {}
    assert data.managed_script_instruction is None
    assert data.managed_script_name is None


def test_runtime_data_holds_both_coordinators() -> None:
    a, b, c = MagicMock(), MagicMock(), MagicMock()
    runtime = XeniaRuntimeData(coordinator=a, config_coordinator=b, shot_store=c)
    assert runtime.coordinator is a
    assert runtime.config_coordinator is b
    assert runtime.shot_store is c


# ===========================================================================
# XeniaDataUpdateCoordinator._async_update_data
# ===========================================================================


async def test_data_coordinator_returns_combined_data() -> None:
    coordinator = _make_data_coordinator()
    result = await coordinator._async_update_data()
    assert isinstance(result, XeniaCoordinatorData)
    assert result.overview.ma_status == MachineStatus.ON


async def test_data_coordinator_calls_both_endpoints() -> None:
    coordinator = _make_data_coordinator()
    await coordinator._async_update_data()
    coordinator.xenia.get_overview.assert_called_once()
    coordinator.xenia.get_overview_single.assert_called_once()


async def test_data_coordinator_raises_update_failed_on_overview_error() -> None:
    xenia = _make_xenia_mock()
    xenia.get_overview = AsyncMock(side_effect=OSError("net"))
    coordinator = _make_data_coordinator(xenia=xenia)
    with pytest.raises(UpdateFailed, match="Xenia fetch failed"):
        await coordinator._async_update_data()


async def test_data_coordinator_raises_update_failed_on_single_error() -> None:
    xenia = _make_xenia_mock()
    xenia.get_overview_single = AsyncMock(side_effect=TimeoutError())
    coordinator = _make_data_coordinator(xenia=xenia)
    with pytest.raises(UpdateFailed, match="Xenia fetch failed: TimeoutError"):
        await coordinator._async_update_data()


# ===========================================================================
# Polling interval per machine state
# ===========================================================================


@pytest.mark.parametrize(
    ("ma_status", "expected"),
    [
        (MachineStatus.BREWING, POLL_INTERVAL_BREWING),
        (MachineStatus.DRAINING, POLL_INTERVAL_BREWING),
        (MachineStatus.ECO, POLL_INTERVAL_IDLE),
        (MachineStatus.OFF, POLL_INTERVAL_IDLE),
        (MachineStatus.UNKNOWN, POLL_INTERVAL_IDLE),
    ],
)
async def test_polling_interval_per_state(ma_status, expected) -> None:
    xenia = _make_xenia_mock(overview={"MA_STATUS": ma_status})
    coordinator = _make_data_coordinator(xenia=xenia)
    await coordinator._async_update_data()
    assert coordinator.update_interval == expected


async def test_polling_interval_ready_when_temps_within_threshold() -> None:
    xenia = _make_xenia_mock(
        overview={
            "MA_STATUS": MachineStatus.ON,
            "BG_SENS_TEMP_A": 93.0,
            "BB_SENS_TEMP_A": 130.0,
        },
        overview_single={"BG_SET_TEMP": 93.5, "BB_SET_TEMP": 130.0},
    )
    coordinator = _make_data_coordinator(xenia=xenia)
    await coordinator._async_update_data()
    assert coordinator.update_interval == POLL_INTERVAL_READY


async def test_polling_interval_heating_when_temps_outside_threshold() -> None:
    xenia = _make_xenia_mock(
        overview={
            "MA_STATUS": MachineStatus.ON,
            "BG_SENS_TEMP_A": 50.0,
            "BB_SENS_TEMP_A": 100.0,
        },
        overview_single={"BG_SET_TEMP": 93.5, "BB_SET_TEMP": 130.0},
    )
    coordinator = _make_data_coordinator(xenia=xenia)
    await coordinator._async_update_data()
    assert coordinator.update_interval == POLL_INTERVAL_HEATING


# ===========================================================================
# XeniaConfigCoordinator._async_update_data
# ===========================================================================


async def test_config_coordinator_returns_config_data() -> None:
    coordinator = _make_config_coordinator()
    result = await coordinator._async_update_data()
    assert isinstance(result, XeniaConfigData)
    assert result.machine is not None


async def test_config_coordinator_merges_builtin_and_user_scripts() -> None:
    xenia = _make_xenia_mock()
    xenia.get_scripts = AsyncMock(return_value={10: "MyShot"})
    coordinator = _make_config_coordinator(xenia=xenia)
    result = await coordinator._async_update_data()
    assert result.scripts == {**BUILTIN_SCRIPTS, 10: "MyShot"}


async def test_config_coordinator_user_script_overrides_builtin() -> None:
    xenia = _make_xenia_mock()
    xenia.get_scripts = AsyncMock(return_value={1: "Custom"})
    coordinator = _make_config_coordinator(xenia=xenia)
    result = await coordinator._async_update_data()
    assert result.scripts[1] == "Custom"


async def test_config_coordinator_stores_switches() -> None:
    coordinator = _make_config_coordinator()
    result = await coordinator._async_update_data()
    assert result.switches == {"SWITCH_SET_LEFT_LEFT_0": 1}


@pytest.mark.parametrize(
    ("broken_attr", "exc"),
    [
        ("get_machine", OSError("unreachable")),
        ("get_scripts", TimeoutError("timeout")),
        ("get_switches", ConnectionError("refused")),
    ],
)
async def test_config_coordinator_raises_update_failed_on_any_error(
    broken_attr, exc
) -> None:
    xenia = _make_xenia_mock()
    setattr(xenia, broken_attr, AsyncMock(side_effect=exc))
    coordinator = _make_config_coordinator(xenia=xenia)
    with pytest.raises(UpdateFailed, match="Xenia config fetch failed"):
        await coordinator._async_update_data()


async def test_config_coordinator_reads_managed_script_when_enabled() -> None:
    xenia = _make_xenia_mock()
    xenia.read_script = AsyncMock(
        return_value={"Content": "1;13;27 45;7;", "Title": "My Shot"}
    )
    coordinator = _make_config_coordinator(
        xenia=xenia, weight_management_enabled=True, managed_script_id=17
    )
    result = await coordinator._async_update_data()
    assert result.managed_script_instruction == "1;13;27 45;7;"
    assert result.managed_script_name == "My Shot"


async def test_config_coordinator_skips_managed_script_when_disabled() -> None:
    xenia = _make_xenia_mock()
    xenia.read_script = AsyncMock()
    coordinator = _make_config_coordinator(xenia=xenia, weight_management_enabled=False)
    result = await coordinator._async_update_data()
    assert result.managed_script_instruction is None
    xenia.read_script.assert_not_called()


async def test_config_coordinator_skips_managed_script_when_no_script_id() -> None:
    xenia = _make_xenia_mock()
    xenia.read_script = AsyncMock()
    coordinator = _make_config_coordinator(xenia=xenia, weight_management_enabled=True)
    result = await coordinator._async_update_data()
    assert result.managed_script_instruction is None
    xenia.read_script.assert_not_called()


async def test_config_coordinator_handles_managed_script_read_failure() -> None:
    xenia = _make_xenia_mock()
    xenia.read_script = AsyncMock(side_effect=OSError("refused"))
    coordinator = _make_config_coordinator(
        xenia=xenia, weight_management_enabled=True, managed_script_id=17
    )
    result = await coordinator._async_update_data()
    assert isinstance(result, XeniaConfigData)
    assert result.managed_script_instruction is None
    assert result.machine is not None
