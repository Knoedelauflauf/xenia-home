"""Tests for switch.py — XeniaPowerSwitch, XeniaEcoSwitch, XeniaSteamBoilerSwitch."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.xenia_home.const import (
    CONF_POWER_ON_BEHAVIOR,
    XENIA_DOMAIN,
    PowerOnBehavior,
)
from custom_components.xenia_home.coordinator import XeniaCoordinatorData
from custom_components.xenia_home.switch import (
    XeniaEcoSwitch,
    XeniaPowerSwitch,
    XeniaSteamBoilerSwitch,
)
from custom_components.xenia_home.xenia import (
    MachineStatus,
    SteamBoilerStatus,
    XeniaOverviewData,
    XeniaOverviewSingleData,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_coordinator(
    ma_status: MachineStatus = MachineStatus.ON,
    sb_status: SteamBoilerStatus = SteamBoilerStatus.ON,
    options: dict | None = None,
) -> MagicMock:
    coord = MagicMock()
    coord.config_entry = MagicMock()
    coord.config_entry.data = {"host": "xenia.local"}
    coord.config_entry.options = options or {}
    coord.xenia = MagicMock()
    coord.xenia.machine_turn_on = AsyncMock()
    coord.xenia.machine_turn_off = AsyncMock()
    coord.xenia.machine_set_eco = AsyncMock()
    coord.xenia.sb_turn_on = AsyncMock()
    coord.xenia.sb_turn_off = AsyncMock()
    coord.async_request_refresh = AsyncMock()

    overview = XeniaOverviewData.from_dict(
        {"MA_STATUS": ma_status.value, "SB_STATUS": sb_status.value}
    )
    coord.data = XeniaCoordinatorData(
        overview=overview,
        overview_single=XeniaOverviewSingleData.from_dict({}),
    )
    return coord


def _make_power_switch(coordinator: MagicMock) -> XeniaPowerSwitch:
    with patch(
        "custom_components.xenia_home.entity.XeniaEntity.__init__", return_value=None
    ):
        sw = XeniaPowerSwitch.__new__(XeniaPowerSwitch)
        sw.coordinator = coordinator
        sw.hass = MagicMock()
        XeniaPowerSwitch.__init__(sw, coordinator)
    return sw


def _make_eco_switch(coordinator: MagicMock) -> XeniaEcoSwitch:
    with patch(
        "custom_components.xenia_home.entity.XeniaEntity.__init__", return_value=None
    ):
        sw = XeniaEcoSwitch.__new__(XeniaEcoSwitch)
        sw.coordinator = coordinator
        sw.hass = MagicMock()
        XeniaEcoSwitch.__init__(sw, coordinator)
    return sw


def _make_steam_switch(coordinator: MagicMock) -> XeniaSteamBoilerSwitch:
    with patch(
        "custom_components.xenia_home.entity.XeniaEntity.__init__", return_value=None
    ):
        sw = XeniaSteamBoilerSwitch.__new__(XeniaSteamBoilerSwitch)
        sw.coordinator = coordinator
        sw.hass = MagicMock()
        XeniaSteamBoilerSwitch.__init__(sw, coordinator)
    return sw


# ===========================================================================
# XeniaPowerSwitch
# ===========================================================================


def test_power_switch_unique_id_includes_domain_and_host() -> None:
    coord = _make_coordinator()
    sw = _make_power_switch(coord)
    assert XENIA_DOMAIN in sw._attr_unique_id
    assert "xenia.local" in sw._attr_unique_id


@pytest.mark.parametrize(
    "status, expected_is_on",
    [
        (MachineStatus.ON, True),
        (MachineStatus.BREWING, True),
        (MachineStatus.DRAINING, True),
        (MachineStatus.OFF, False),
        (MachineStatus.ECO, False),
        (MachineStatus.UNKNOWN, False),
    ],
)
def test_power_switch_is_on_for_status(
    status: MachineStatus, expected_is_on: bool
) -> None:
    coord = _make_coordinator(ma_status=status)
    sw = _make_power_switch(coord)
    assert sw.is_on == expected_is_on


@pytest.mark.asyncio
async def test_power_switch_turn_on_steam_on_calls_machine_turn_on() -> None:
    coord = _make_coordinator(
        options={CONF_POWER_ON_BEHAVIOR: PowerOnBehavior.STEAM_ON}
    )
    sw = _make_power_switch(coord)
    await sw.async_turn_on()
    coord.xenia.machine_turn_on.assert_called_once()
    # Default call with no args means sb_on=True
    call_kwargs = coord.xenia.machine_turn_on.call_args
    assert call_kwargs is not None


@pytest.mark.asyncio
async def test_power_switch_turn_on_steam_off_calls_machine_turn_on_false() -> None:
    coord = _make_coordinator(
        options={CONF_POWER_ON_BEHAVIOR: PowerOnBehavior.STEAM_OFF}
    )
    sw = _make_power_switch(coord)
    await sw.async_turn_on()
    coord.xenia.machine_turn_on.assert_called_once_with(False)


@pytest.mark.asyncio
async def test_power_switch_turn_on_default_behavior_is_steam_off() -> None:
    # No option stored — DEFAULT_POWER_ON_BEHAVIOR is STEAM_OFF
    coord = _make_coordinator(options={})
    sw = _make_power_switch(coord)
    await sw.async_turn_on()
    coord.xenia.machine_turn_on.assert_called_once_with(False)


@pytest.mark.asyncio
async def test_power_switch_turn_on_refreshes_coordinator() -> None:
    coord = _make_coordinator(
        options={CONF_POWER_ON_BEHAVIOR: PowerOnBehavior.STEAM_OFF}
    )
    sw = _make_power_switch(coord)
    await sw.async_turn_on()
    coord.async_request_refresh.assert_called_once()


@pytest.mark.asyncio
async def test_power_switch_turn_off_calls_machine_turn_off() -> None:
    coord = _make_coordinator()
    sw = _make_power_switch(coord)
    await sw.async_turn_off()
    coord.xenia.machine_turn_off.assert_called_once()


@pytest.mark.asyncio
async def test_power_switch_turn_off_refreshes_coordinator() -> None:
    coord = _make_coordinator()
    sw = _make_power_switch(coord)
    await sw.async_turn_off()
    coord.async_request_refresh.assert_called_once()


# ===========================================================================
# XeniaEcoSwitch
# ===========================================================================


def test_eco_switch_unique_id_includes_eco_mode() -> None:
    coord = _make_coordinator()
    sw = _make_eco_switch(coord)
    assert "eco_mode" in sw._attr_unique_id


@pytest.mark.parametrize(
    "status, expected_is_on",
    [
        (MachineStatus.ECO, True),
        (MachineStatus.ON, False),
        (MachineStatus.BREWING, False),
        (MachineStatus.OFF, False),
        (MachineStatus.UNKNOWN, False),
    ],
)
def test_eco_switch_is_on_only_for_eco_status(
    status: MachineStatus, expected_is_on: bool
) -> None:
    coord = _make_coordinator(ma_status=status)
    sw = _make_eco_switch(coord)
    assert sw.is_on == expected_is_on


@pytest.mark.parametrize(
    "status, expected_available",
    [
        (MachineStatus.ON, True),
        (MachineStatus.BREWING, True),
        (MachineStatus.DRAINING, True),
        (MachineStatus.ECO, True),
        (MachineStatus.OFF, False),
        (MachineStatus.UNKNOWN, False),
    ],
)
def test_eco_switch_available_for_active_states(
    status: MachineStatus, expected_available: bool
) -> None:
    coord = _make_coordinator(ma_status=status)
    sw = _make_eco_switch(coord)
    assert sw.available == expected_available


@pytest.mark.asyncio
async def test_eco_switch_turn_on_calls_machine_set_eco() -> None:
    coord = _make_coordinator()
    sw = _make_eco_switch(coord)
    with patch("asyncio.sleep", new_callable=AsyncMock):
        await sw.async_turn_on()
    coord.xenia.machine_set_eco.assert_called_once()


@pytest.mark.asyncio
async def test_eco_switch_turn_off_steam_on_calls_machine_turn_on() -> None:
    coord = _make_coordinator(
        ma_status=MachineStatus.ECO,
        options={CONF_POWER_ON_BEHAVIOR: PowerOnBehavior.STEAM_ON},
    )
    sw = _make_eco_switch(coord)
    with patch("asyncio.sleep", new_callable=AsyncMock):
        await sw.async_turn_off()
    coord.xenia.machine_turn_on.assert_called_once()


@pytest.mark.asyncio
async def test_eco_switch_turn_off_steam_off_calls_machine_turn_on_false() -> None:
    coord = _make_coordinator(
        ma_status=MachineStatus.ECO,
        options={CONF_POWER_ON_BEHAVIOR: PowerOnBehavior.STEAM_OFF},
    )
    sw = _make_eco_switch(coord)
    with patch("asyncio.sleep", new_callable=AsyncMock):
        await sw.async_turn_off()
    coord.xenia.machine_turn_on.assert_called_once_with(False)


@pytest.mark.asyncio
async def test_eco_switch_turn_on_refreshes_coordinator() -> None:
    coord = _make_coordinator()
    sw = _make_eco_switch(coord)
    with patch("asyncio.sleep", new_callable=AsyncMock):
        await sw.async_turn_on()
    coord.async_request_refresh.assert_called_once()


# ===========================================================================
# XeniaSteamBoilerSwitch
# ===========================================================================


def test_steam_boiler_switch_unique_id_includes_steam_boiler_power() -> None:
    coord = _make_coordinator()
    sw = _make_steam_switch(coord)
    assert "steam_boiler_power" in sw._attr_unique_id


@pytest.mark.parametrize(
    "sb_status, expected_is_on",
    [
        (SteamBoilerStatus.ON, True),
        (SteamBoilerStatus.OFF, False),
        (SteamBoilerStatus.UNKNOWN, False),
    ],
)
def test_steam_boiler_switch_is_on_for_status(
    sb_status: SteamBoilerStatus, expected_is_on: bool
) -> None:
    coord = _make_coordinator(sb_status=sb_status)
    sw = _make_steam_switch(coord)
    assert sw.is_on == expected_is_on


@pytest.mark.parametrize(
    "ma_status, expected_available",
    [
        (MachineStatus.ON, True),
        (MachineStatus.BREWING, True),
        (MachineStatus.DRAINING, True),
        (MachineStatus.ECO, False),
        (MachineStatus.OFF, False),
        (MachineStatus.UNKNOWN, False),
    ],
)
def test_steam_boiler_switch_available_only_when_machine_on(
    ma_status: MachineStatus, expected_available: bool
) -> None:
    coord = _make_coordinator(ma_status=ma_status)
    sw = _make_steam_switch(coord)
    assert sw.available == expected_available


@pytest.mark.asyncio
async def test_steam_boiler_switch_turn_on_calls_sb_turn_on() -> None:
    coord = _make_coordinator()
    sw = _make_steam_switch(coord)
    with patch("asyncio.sleep", new_callable=AsyncMock):
        await sw.async_turn_on()
    coord.xenia.sb_turn_on.assert_called_once()


@pytest.mark.asyncio
async def test_steam_boiler_switch_turn_off_calls_sb_turn_off() -> None:
    coord = _make_coordinator()
    sw = _make_steam_switch(coord)
    with patch("asyncio.sleep", new_callable=AsyncMock):
        await sw.async_turn_off()
    coord.xenia.sb_turn_off.assert_called_once()


@pytest.mark.asyncio
async def test_steam_boiler_switch_turn_on_refreshes_coordinator() -> None:
    coord = _make_coordinator()
    sw = _make_steam_switch(coord)
    with patch("asyncio.sleep", new_callable=AsyncMock):
        await sw.async_turn_on()
    coord.async_request_refresh.assert_called_once()


@pytest.mark.asyncio
async def test_steam_boiler_switch_turn_off_refreshes_coordinator() -> None:
    coord = _make_coordinator()
    sw = _make_steam_switch(coord)
    with patch("asyncio.sleep", new_callable=AsyncMock):
        await sw.async_turn_off()
    coord.async_request_refresh.assert_called_once()
