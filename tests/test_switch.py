"""Tests for switch.py — XeniaPowerSwitch, XeniaEcoSwitch, XeniaSteamBoilerSwitch."""

from __future__ import annotations

import pytest

from custom_components.xenia_home.const import (
    CONF_POWER_ON_BEHAVIOR,
    PowerOnBehavior,
)
from custom_components.xenia_home.xenia import MachineStatus, SteamBoilerStatus


POWER = "switch.xenia_espresso_machine_power"
ECO = "switch.xenia_espresso_machine_eco_mode"
STEAM_BOILER = "switch.xenia_espresso_machine_steam_boiler_power"


async def test_switch_entities_snapshot(
    hass, init_integration, snapshot, entity_registry
):
    entity_ids = sorted(
        e.entity_id
        for e in entity_registry.entities.values()
        if e.platform == "xenia_home" and e.domain == "switch"
    )
    assert len(entity_ids) == 3
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        registry_entry = entity_registry.async_get(entity_id)
        assert state == snapshot(name=f"{entity_id}-state")
        assert registry_entry == snapshot(name=f"{entity_id}-registry")


# ===========================================================================
# Power switch — is_on for each MachineStatus
# ===========================================================================


@pytest.mark.parametrize(
    "ma_status, expected_state",
    [
        (MachineStatus.ON, "on"),
        (MachineStatus.BREWING, "on"),
        (MachineStatus.DRAINING, "on"),
        (MachineStatus.OFF, "off"),
        (MachineStatus.ECO, "off"),
        (MachineStatus.UNKNOWN, "off"),
    ],
)
async def test_power_switch_state(
    hass,
    enable_custom_integrations,
    mock_xenia_api,
    mock_config_entry,
    ma_status,
    expected_state,
):
    mock_xenia_api.set_overview(MA_STATUS=int(ma_status))
    mock_xenia_api.register()
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(POWER).state == expected_state


async def test_power_switch_turn_on_steam_on_calls_machine_on(
    hass,
    enable_custom_integrations,
    mock_xenia_api,
    mock_config_entry_factory_with_options,
):
    entry = mock_config_entry_factory_with_options(
        {CONF_POWER_ON_BEHAVIOR: PowerOnBehavior.STEAM_ON}
    )
    mock_xenia_api.expect_machine_control()
    mock_xenia_api.register()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": POWER}, blocking=True
    )
    await hass.async_block_till_done()
    # MachineControl.ON = 1
    mock_xenia_api.assert_post_called_with("machine/control", '"1"')


async def test_power_switch_turn_on_steam_off_calls_on_sb_off(
    hass,
    enable_custom_integrations,
    mock_xenia_api,
    mock_config_entry_factory_with_options,
):
    entry = mock_config_entry_factory_with_options(
        {CONF_POWER_ON_BEHAVIOR: PowerOnBehavior.STEAM_OFF}
    )
    mock_xenia_api.expect_machine_control()
    mock_xenia_api.register()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": POWER}, blocking=True
    )
    await hass.async_block_till_done()
    # MachineControl.ON_SB_OFF = 5
    mock_xenia_api.assert_post_called_with("machine/control", '"5"')


async def test_power_switch_turn_on_default_behavior_is_steam_off(
    hass, init_integration, mock_xenia_api
):
    mock_xenia_api.expect_machine_control()
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": POWER}, blocking=True
    )
    await hass.async_block_till_done()
    mock_xenia_api.assert_post_called_with("machine/control", '"5"')


async def test_power_switch_turn_off_calls_machine_off(
    hass, init_integration, mock_xenia_api
):
    mock_xenia_api.expect_machine_control()
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": POWER}, blocking=True
    )
    await hass.async_block_till_done()
    # MachineControl.OFF = 0
    mock_xenia_api.assert_post_called_with("machine/control", '"0"')


# ===========================================================================
# Eco switch
# ===========================================================================


@pytest.mark.parametrize(
    "ma_status, expected_state",
    [
        (MachineStatus.ECO, "on"),
        (MachineStatus.ON, "off"),
        (MachineStatus.BREWING, "off"),
        (MachineStatus.OFF, "unavailable"),
        (MachineStatus.UNKNOWN, "unavailable"),
    ],
)
async def test_eco_switch_state(
    hass,
    enable_custom_integrations,
    mock_xenia_api,
    mock_config_entry,
    ma_status,
    expected_state,
):
    mock_xenia_api.set_overview(MA_STATUS=int(ma_status))
    mock_xenia_api.register()
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(ECO).state == expected_state


async def test_eco_switch_turn_on_calls_machine_set_eco(
    hass, init_integration, mock_xenia_api
):
    mock_xenia_api.expect_machine_control()
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": ECO}, blocking=True
    )
    await hass.async_block_till_done()
    # MachineControl.ECO = 2
    mock_xenia_api.assert_post_called_with("machine/control", '"2"')


async def test_eco_switch_turn_off_steam_off_calls_on_sb_off(
    hass,
    enable_custom_integrations,
    mock_xenia_api,
    mock_config_entry_factory_with_options,
):
    entry = mock_config_entry_factory_with_options(
        {CONF_POWER_ON_BEHAVIOR: PowerOnBehavior.STEAM_OFF}
    )
    mock_xenia_api.set_overview(MA_STATUS=int(MachineStatus.ECO))
    mock_xenia_api.expect_machine_control()
    mock_xenia_api.register()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": ECO}, blocking=True
    )
    await hass.async_block_till_done()
    mock_xenia_api.assert_post_called_with("machine/control", '"5"')


# ===========================================================================
# Steam boiler switch
# ===========================================================================


@pytest.mark.parametrize(
    "sb_status, expected_state",
    [
        (SteamBoilerStatus.ON, "on"),
        (SteamBoilerStatus.OFF, "off"),
    ],
)
async def test_steam_boiler_state(
    hass,
    enable_custom_integrations,
    mock_xenia_api,
    mock_config_entry,
    sb_status,
    expected_state,
):
    mock_xenia_api.set_overview(
        SB_STATUS=int(sb_status), MA_STATUS=int(MachineStatus.ON)
    )
    mock_xenia_api.register()
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(STEAM_BOILER).state == expected_state


@pytest.mark.parametrize(
    "ma_status, expected_avail",
    [
        (MachineStatus.ON, True),
        (MachineStatus.BREWING, True),
        (MachineStatus.ECO, False),
        (MachineStatus.OFF, False),
    ],
)
async def test_steam_boiler_availability_follows_machine_state(
    hass,
    enable_custom_integrations,
    mock_xenia_api,
    mock_config_entry,
    ma_status,
    expected_avail,
):
    mock_xenia_api.set_overview(MA_STATUS=int(ma_status))
    mock_xenia_api.register()
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get(STEAM_BOILER)
    assert state is not None
    is_available = state.state not in ("unavailable", "unknown")
    assert is_available == expected_avail


async def test_steam_boiler_turn_on_calls_toggle_sb(
    hass, init_integration, mock_xenia_api
):
    mock_xenia_api.expect_toggle_sb()
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": STEAM_BOILER}, blocking=True
    )
    await hass.async_block_till_done()
    mock_xenia_api.assert_post_called_with("toggle_sb", "true")


async def test_steam_boiler_turn_off_calls_toggle_sb(
    hass, init_integration, mock_xenia_api
):
    mock_xenia_api.expect_toggle_sb()
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": STEAM_BOILER}, blocking=True
    )
    await hass.async_block_till_done()
    mock_xenia_api.assert_post_called_with("toggle_sb", "false")
