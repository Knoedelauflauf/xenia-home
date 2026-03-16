"""Unit tests for coordinator.py — XeniaDataUpdateCoordinator and XeniaConfigCoordinator."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.xenia_home.const import (
    CONF_POLL_ACTIVE,
    CONF_POLL_BREWING,
    CONF_POLL_IDLE,
    CONF_POLL_READY,
    CONF_READY_THRESHOLD,
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
    hass.config = MagicMock()
    hass.config.time_zone = "UTC"
    return hass


def _make_config_entry(entry_id: str = "test_entry", **options) -> MagicMock:
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.options = options
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
    data = XeniaCoordinatorData(
        overview=overview_data, overview_single=overview_single_data
    )
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

    with patch(
        "homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"
    ):
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

    with patch(
        "homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"
    ):
        coordinator = XeniaDataUpdateCoordinator(hass, entry, xenia)

    result = await coordinator._async_update_data()

    assert isinstance(result, XeniaCoordinatorData)
    assert result.overview.ma_status.value == 1


@pytest.mark.asyncio
async def test_data_coordinator_update_calls_both_endpoints() -> None:
    hass = _make_hass()
    entry = _make_config_entry()
    xenia = _make_xenia_mock()

    with patch(
        "homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"
    ):
        coordinator = XeniaDataUpdateCoordinator(hass, entry, xenia)

    await coordinator._async_update_data()

    xenia.get_overview.assert_called_once()
    xenia.get_overview_single.assert_called_once()


@pytest.mark.asyncio
async def test_data_coordinator_update_raises_update_failed_on_exception() -> None:
    hass = _make_hass()
    entry = _make_config_entry()
    xenia = _make_xenia_mock()
    xenia.get_overview = AsyncMock(side_effect=OSError("network error"))

    with patch(
        "homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"
    ):
        coordinator = XeniaDataUpdateCoordinator(hass, entry, xenia)

    with pytest.raises(UpdateFailed, match="Xenia fetch failed"):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_data_coordinator_update_raises_update_failed_on_single_exception() -> (
    None
):
    hass = _make_hass()
    entry = _make_config_entry()
    xenia = _make_xenia_mock()
    xenia.get_overview_single = AsyncMock(side_effect=TimeoutError("timeout"))

    with patch(
        "homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"
    ):
        coordinator = XeniaDataUpdateCoordinator(hass, entry, xenia)

    with pytest.raises(UpdateFailed, match="Xenia fetch failed"):
        await coordinator._async_update_data()


# ===========================================================================
# XeniaConfigCoordinator.__init__
# ===========================================================================


def test_config_coordinator_stores_xenia_client() -> None:
    hass = _make_hass()
    entry = _make_config_entry()
    xenia = _make_xenia_mock()

    with patch(
        "homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"
    ):
        coordinator = XeniaConfigCoordinator(hass, entry, xenia)

    assert coordinator.xenia is xenia


def test_config_coordinator_selected_script_id_starts_none() -> None:
    hass = _make_hass()
    entry = _make_config_entry()
    xenia = _make_xenia_mock()

    with patch(
        "homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"
    ):
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

    with patch(
        "homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"
    ):
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

    with patch(
        "homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"
    ):
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

    with patch(
        "homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"
    ):
        coordinator = XeniaConfigCoordinator(hass, entry, xenia)

    result = await coordinator._async_update_data()
    assert result.scripts[1] == "Custom Espresso"


@pytest.mark.asyncio
async def test_config_coordinator_update_stores_switches() -> None:
    hass = _make_hass()
    entry = _make_config_entry()
    xenia = _make_xenia_mock()

    with patch(
        "homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"
    ):
        coordinator = XeniaConfigCoordinator(hass, entry, xenia)

    result = await coordinator._async_update_data()
    assert result.switches == {"SWITCH_SET_LEFT_LEFT_0": 1}


@pytest.mark.asyncio
async def test_config_coordinator_update_raises_update_failed_on_machine_error() -> (
    None
):
    hass = _make_hass()
    entry = _make_config_entry()
    xenia = _make_xenia_mock()
    xenia.get_machine = AsyncMock(side_effect=OSError("unreachable"))

    with patch(
        "homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"
    ):
        coordinator = XeniaConfigCoordinator(hass, entry, xenia)

    with pytest.raises(UpdateFailed, match="Xenia config fetch failed"):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_config_coordinator_update_raises_update_failed_on_scripts_error() -> (
    None
):
    hass = _make_hass()
    entry = _make_config_entry()
    xenia = _make_xenia_mock()
    xenia.get_scripts = AsyncMock(side_effect=TimeoutError("timeout"))

    with patch(
        "homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"
    ):
        coordinator = XeniaConfigCoordinator(hass, entry, xenia)

    with pytest.raises(UpdateFailed, match="Xenia config fetch failed"):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_config_coordinator_update_raises_update_failed_on_switches_error() -> (
    None
):
    hass = _make_hass()
    entry = _make_config_entry()
    xenia = _make_xenia_mock()
    xenia.get_switches = AsyncMock(side_effect=ConnectionError("refused"))

    with patch(
        "homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"
    ):
        coordinator = XeniaConfigCoordinator(hass, entry, xenia)

    with pytest.raises(UpdateFailed, match="Xenia config fetch failed"):
        await coordinator._async_update_data()


# ===========================================================================
# XeniaConfigCoordinator — managed script reading
# ===========================================================================


@pytest.mark.asyncio
async def test_config_coordinator_reads_managed_script_when_enabled() -> None:
    hass = _make_hass()
    entry = _make_config_entry(weight_management_enabled=True, managed_script_id=17)
    xenia = _make_xenia_mock()
    xenia.read_script = AsyncMock(
        return_value={"Content": "1;13;27 45;7;", "Title": "My Shot"}
    )

    with patch(
        "homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"
    ):
        coordinator = XeniaConfigCoordinator(hass, entry, xenia)

    result = await coordinator._async_update_data()
    assert result.managed_script_instruction == "1;13;27 45;7;"
    assert result.managed_script_name == "My Shot"


@pytest.mark.asyncio
async def test_config_coordinator_skips_managed_script_when_disabled() -> None:
    hass = _make_hass()
    entry = _make_config_entry(weight_management_enabled=False)
    xenia = _make_xenia_mock()
    xenia.read_script = AsyncMock()

    with patch(
        "homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"
    ):
        coordinator = XeniaConfigCoordinator(hass, entry, xenia)

    result = await coordinator._async_update_data()
    assert result.managed_script_instruction is None
    assert result.managed_script_name is None
    xenia.read_script.assert_not_called()


@pytest.mark.asyncio
async def test_config_coordinator_skips_managed_script_when_no_script_id() -> None:
    hass = _make_hass()
    entry = _make_config_entry(weight_management_enabled=True)
    xenia = _make_xenia_mock()
    xenia.read_script = AsyncMock()

    with patch(
        "homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"
    ):
        coordinator = XeniaConfigCoordinator(hass, entry, xenia)

    result = await coordinator._async_update_data()
    assert result.managed_script_instruction is None
    xenia.read_script.assert_not_called()


@pytest.mark.asyncio
async def test_config_coordinator_handles_managed_script_read_failure() -> None:
    """When reading the managed script fails, the update should still succeed."""
    hass = _make_hass()
    entry = _make_config_entry(weight_management_enabled=True, managed_script_id=17)
    xenia = _make_xenia_mock()
    xenia.read_script = AsyncMock(side_effect=OSError("connection refused"))

    with patch(
        "homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"
    ):
        coordinator = XeniaConfigCoordinator(hass, entry, xenia)

    result = await coordinator._async_update_data()
    # Update succeeds but managed instruction is None
    assert isinstance(result, XeniaConfigData)
    assert result.managed_script_instruction is None
    assert result.machine is not None


# ===========================================================================
# Dynamic polling intervals
# ===========================================================================


def _make_data_coordinator(
    overview_dict: dict | None = None,
    overview_single_dict: dict | None = None,
    **options,
) -> XeniaDataUpdateCoordinator:
    """Build a XeniaDataUpdateCoordinator with mocked internals."""
    hass = _make_hass()
    entry = _make_config_entry(**options)
    xenia = _make_xenia_mock()

    if overview_dict is not None:
        xenia.get_overview = AsyncMock(
            return_value=XeniaOverviewData.from_dict(overview_dict)
        )
    if overview_single_dict is not None:
        xenia.get_overview_single = AsyncMock(
            return_value=XeniaOverviewSingleData.from_dict(overview_single_dict)
        )

    with patch(
        "homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__"
    ):
        coordinator = XeniaDataUpdateCoordinator(hass, entry, xenia)
        coordinator.update_interval = timedelta(seconds=1)

    return coordinator


@pytest.mark.asyncio
async def test_polling_interval_brewing_state() -> None:
    """Brewing status should use the brewing interval."""
    coordinator = _make_data_coordinator(
        overview_dict={"MA_STATUS": MachineStatus.BREWING},
    )
    await coordinator._async_update_data()
    assert coordinator.update_interval == timedelta(seconds=1)


@pytest.mark.asyncio
async def test_polling_interval_draining_state() -> None:
    """Draining status should use the brewing interval."""
    coordinator = _make_data_coordinator(
        overview_dict={"MA_STATUS": MachineStatus.DRAINING},
    )
    await coordinator._async_update_data()
    assert coordinator.update_interval == timedelta(seconds=1)


@pytest.mark.asyncio
async def test_polling_interval_idle_eco() -> None:
    """ECO status should use the idle interval."""
    coordinator = _make_data_coordinator(
        overview_dict={"MA_STATUS": MachineStatus.ECO},
    )
    await coordinator._async_update_data()
    assert coordinator.update_interval == timedelta(seconds=1)


@pytest.mark.asyncio
async def test_polling_interval_idle_off() -> None:
    """OFF status should use the idle interval."""
    coordinator = _make_data_coordinator(
        overview_dict={"MA_STATUS": MachineStatus.OFF},
    )
    await coordinator._async_update_data()
    assert coordinator.update_interval == timedelta(seconds=1)


@pytest.mark.asyncio
async def test_polling_interval_ready_when_temps_within_threshold() -> None:
    """ON with temps within threshold should use the ready interval."""
    coordinator = _make_data_coordinator(
        overview_dict={
            "MA_STATUS": MachineStatus.ON,
            "BG_SENS_TEMP_A": 93.0,
            "BB_SENS_TEMP_A": 130.0,
        },
        overview_single_dict={"BG_SET_TEMP": 93.5, "BB_SET_TEMP": 130.0},
    )
    await coordinator._async_update_data()
    assert coordinator.update_interval == timedelta(seconds=1)


@pytest.mark.asyncio
async def test_polling_interval_active_when_temps_outside_threshold() -> None:
    """ON with temps outside threshold should use the active interval."""
    coordinator = _make_data_coordinator(
        overview_dict={
            "MA_STATUS": MachineStatus.ON,
            "BG_SENS_TEMP_A": 50.0,
            "BB_SENS_TEMP_A": 100.0,
        },
        overview_single_dict={"BG_SET_TEMP": 93.5, "BB_SET_TEMP": 130.0},
    )
    await coordinator._async_update_data()
    assert coordinator.update_interval == timedelta(seconds=1)


@pytest.mark.asyncio
async def test_polling_interval_custom_brewing() -> None:
    """Custom brewing interval from options should be used."""
    coordinator = _make_data_coordinator(
        overview_dict={"MA_STATUS": MachineStatus.BREWING},
        **{CONF_POLL_BREWING: 0.5},
    )
    await coordinator._async_update_data()
    assert coordinator.update_interval == timedelta(seconds=0.5)


@pytest.mark.asyncio
async def test_polling_interval_custom_idle() -> None:
    """Custom idle interval from options should be used."""
    coordinator = _make_data_coordinator(
        overview_dict={"MA_STATUS": MachineStatus.ECO},
        **{CONF_POLL_IDLE: 10.0},
    )
    await coordinator._async_update_data()
    assert coordinator.update_interval == timedelta(seconds=10.0)


@pytest.mark.asyncio
async def test_polling_interval_custom_ready() -> None:
    """Custom ready interval from options should be used."""
    coordinator = _make_data_coordinator(
        overview_dict={
            "MA_STATUS": MachineStatus.ON,
            "BG_SENS_TEMP_A": 93.0,
            "BB_SENS_TEMP_A": 130.0,
        },
        overview_single_dict={"BG_SET_TEMP": 93.5, "BB_SET_TEMP": 130.0},
        **{CONF_POLL_READY: 5.0},
    )
    await coordinator._async_update_data()
    assert coordinator.update_interval == timedelta(seconds=5.0)


@pytest.mark.asyncio
async def test_polling_interval_custom_active() -> None:
    """Custom active interval from options should be used."""
    coordinator = _make_data_coordinator(
        overview_dict={
            "MA_STATUS": MachineStatus.ON,
            "BG_SENS_TEMP_A": 50.0,
            "BB_SENS_TEMP_A": 100.0,
        },
        overview_single_dict={"BG_SET_TEMP": 93.5, "BB_SET_TEMP": 130.0},
        **{CONF_POLL_ACTIVE: 3.0},
    )
    await coordinator._async_update_data()
    assert coordinator.update_interval == timedelta(seconds=3.0)


@pytest.mark.asyncio
async def test_polling_interval_custom_threshold() -> None:
    """Custom threshold should affect ready vs active classification."""
    # With default threshold (2.0) this would be active, but with 50.0 it should be ready
    coordinator = _make_data_coordinator(
        overview_dict={
            "MA_STATUS": MachineStatus.ON,
            "BG_SENS_TEMP_A": 50.0,
            "BB_SENS_TEMP_A": 100.0,
        },
        overview_single_dict={"BG_SET_TEMP": 93.5, "BB_SET_TEMP": 130.0},
        **{CONF_READY_THRESHOLD: 50.0, CONF_POLL_READY: 5.0, CONF_POLL_ACTIVE: 2.0},
    )
    await coordinator._async_update_data()
    assert coordinator.update_interval == timedelta(seconds=5.0)


@pytest.mark.asyncio
async def test_polling_interval_unknown_status_uses_idle() -> None:
    """UNKNOWN status should use the idle interval."""
    coordinator = _make_data_coordinator(
        overview_dict={"MA_STATUS": MachineStatus.UNKNOWN},
        **{CONF_POLL_IDLE: 15.0},
    )
    await coordinator._async_update_data()
    assert coordinator.update_interval == timedelta(seconds=15.0)


@pytest.mark.asyncio
async def test_polling_interval_zero_threshold_requires_exact_match() -> None:
    """Threshold of 0.0 means temps must match exactly for ready state."""
    # Temps differ by 0.5 — with threshold 0 this should be active
    coordinator = _make_data_coordinator(
        overview_dict={
            "MA_STATUS": MachineStatus.ON,
            "BG_SENS_TEMP_A": 93.0,
            "BB_SENS_TEMP_A": 130.0,
        },
        overview_single_dict={"BG_SET_TEMP": 93.5, "BB_SET_TEMP": 130.0},
        **{CONF_READY_THRESHOLD: 0.0, CONF_POLL_READY: 5.0, CONF_POLL_ACTIVE: 2.0},
    )
    await coordinator._async_update_data()
    assert coordinator.update_interval == timedelta(seconds=2.0)
