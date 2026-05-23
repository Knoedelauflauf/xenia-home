"""Tests for coordinator.py — fast and config coordinators."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.helpers.update_coordinator import UpdateFailed
import pytest

from custom_components.xenia_home.const import (
    CONF_POLL_ACTIVE,
    CONF_POLL_BREWING,
    CONF_POLL_IDLE,
    CONF_POLL_READY,
    CONF_READY_THRESHOLD,
    DEFAULT_POLL_ACTIVE,
    DEFAULT_POLL_BREWING,
    DEFAULT_POLL_IDLE,
    DEFAULT_POLL_READY,
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
    a, b = MagicMock(), MagicMock()
    runtime = XeniaRuntimeData(coordinator=a, config_coordinator=b)
    assert runtime.coordinator is a
    assert runtime.config_coordinator is b


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
    xenia.get_overview_single = AsyncMock(side_effect=TimeoutError("timeout"))
    coordinator = _make_data_coordinator(xenia=xenia)
    with pytest.raises(UpdateFailed, match="Xenia fetch failed"):
        await coordinator._async_update_data()


# ===========================================================================
# Dynamic polling intervals — REAL test of the match statement
#
# Trick: pass distinct overrides for all four CONF_POLL_* keys so the
# four expected intervals differ and the assertion truly distinguishes
# them. With the production defaults of (1.0, 1.0, 1.0, 1.0), tests
# cannot tell brewing from idle.
# ===========================================================================


POLL_OPTS_DISTINCT = {
    CONF_POLL_BREWING: 0.5,
    CONF_POLL_ACTIVE: 2.0,
    CONF_POLL_READY: 5.0,
    CONF_POLL_IDLE: 10.0,
    CONF_READY_THRESHOLD: 2.0,
}


@pytest.mark.parametrize(
    ("ma_status", "expected_seconds"),
    [
        (MachineStatus.BREWING, 0.5),
        (MachineStatus.DRAINING, 0.5),
        (MachineStatus.ECO, 10.0),
        (MachineStatus.OFF, 10.0),
        (MachineStatus.UNKNOWN, 10.0),
    ],
)
async def test_polling_interval_per_state_with_distinct_options(
    ma_status, expected_seconds
) -> None:
    xenia = _make_xenia_mock(overview={"MA_STATUS": ma_status})
    coordinator = _make_data_coordinator(xenia=xenia, **POLL_OPTS_DISTINCT)
    await coordinator._async_update_data()
    assert coordinator.update_interval == timedelta(seconds=expected_seconds)


async def test_polling_interval_ready_when_temps_within_threshold() -> None:
    xenia = _make_xenia_mock(
        overview={
            "MA_STATUS": MachineStatus.ON,
            "BG_SENS_TEMP_A": 93.0,
            "BB_SENS_TEMP_A": 130.0,
        },
        overview_single={"BG_SET_TEMP": 93.5, "BB_SET_TEMP": 130.0},
    )
    coordinator = _make_data_coordinator(xenia=xenia, **POLL_OPTS_DISTINCT)
    await coordinator._async_update_data()
    assert coordinator.update_interval == timedelta(seconds=5.0)  # READY


async def test_polling_interval_active_when_temps_outside_threshold() -> None:
    xenia = _make_xenia_mock(
        overview={
            "MA_STATUS": MachineStatus.ON,
            "BG_SENS_TEMP_A": 50.0,
            "BB_SENS_TEMP_A": 100.0,
        },
        overview_single={"BG_SET_TEMP": 93.5, "BB_SET_TEMP": 130.0},
    )
    coordinator = _make_data_coordinator(xenia=xenia, **POLL_OPTS_DISTINCT)
    await coordinator._async_update_data()
    assert coordinator.update_interval == timedelta(seconds=2.0)  # ACTIVE


async def test_polling_interval_zero_threshold_requires_exact_match() -> None:
    """Threshold 0 means even 0.5°C off counts as ACTIVE."""
    xenia = _make_xenia_mock(
        overview={
            "MA_STATUS": MachineStatus.ON,
            "BG_SENS_TEMP_A": 93.0,
            "BB_SENS_TEMP_A": 130.0,
        },
        overview_single={"BG_SET_TEMP": 93.5, "BB_SET_TEMP": 130.0},
    )
    opts = {**POLL_OPTS_DISTINCT, CONF_READY_THRESHOLD: 0.0}
    coordinator = _make_data_coordinator(xenia=xenia, **opts)
    await coordinator._async_update_data()
    assert coordinator.update_interval == timedelta(seconds=2.0)  # ACTIVE


async def test_polling_interval_uses_defaults_when_options_absent() -> None:
    """With no options, all four defaults are equal — interval becomes default."""
    xenia = _make_xenia_mock(overview={"MA_STATUS": MachineStatus.BREWING})
    coordinator = _make_data_coordinator(xenia=xenia)
    await coordinator._async_update_data()
    assert coordinator.update_interval == timedelta(seconds=DEFAULT_POLL_BREWING)


def test_default_poll_constants_are_documented_to_be_equal() -> None:
    """Guard the contract that all four poll defaults stay numerically equal.

    If this fails, the parametrized distinct-options tests above may need
    review — they intentionally rely on the four defaults being interchangeable
    for the "no options" case but distinct under explicit overrides.
    """
    assert (
        DEFAULT_POLL_BREWING
        == DEFAULT_POLL_ACTIVE
        == DEFAULT_POLL_READY
        == DEFAULT_POLL_IDLE
    )


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
