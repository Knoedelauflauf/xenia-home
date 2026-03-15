"""Tests for select.py — PowerOnBehaviorSelect, ScriptSelect, SwitchConfigSelect."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.xenia_home.const import (
    CONF_POWER_ON_BEHAVIOR,
    DEFAULT_POWER_ON_BEHAVIOR,
    POWER_ON_BEHAVIOR_OPTIONS,
    PowerOnBehavior,
    XENIA_DOMAIN,
)
from custom_components.xenia_home.coordinator import XeniaConfigData
from custom_components.xenia_home.select import (
    SWITCH_TYPES,
    PowerOnBehaviorSelect,
    ScriptSelect,
    SwitchConfigSelect,
    SwitchDescription,
)
from custom_components.xenia_home.xenia import XeniaMachineData


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_coordinator(
    scripts: dict | None = None,
    switches: dict | None = None,
    options: dict | None = None,
) -> MagicMock:
    coordinator = MagicMock()
    coordinator.config_entry = MagicMock()
    coordinator.config_entry.data = {"host": "xenia.local"}
    coordinator.config_entry.options = options or {}

    config_data = XeniaConfigData(
        machine=XeniaMachineData.from_dict({}),
        scripts=scripts or {0: "None", 1: "Espresso", 10: "MyShot"},
        switches=switches or {"SWITCH_SET_LEFT_LEFT_0": 1},
    )
    config_coord = MagicMock()
    config_coord.data = config_data
    config_coord.selected_script_id = None
    config_coord.async_request_refresh = AsyncMock()

    runtime_data = MagicMock()
    runtime_data.config_coordinator = config_coord
    coordinator.config_entry.runtime_data = runtime_data

    return coordinator


# ===========================================================================
# SwitchDescription dataclass
# ===========================================================================


def test_switch_description_is_frozen() -> None:
    desc = SwitchDescription(key="K", translation_key="t")
    with pytest.raises((AttributeError, TypeError)):
        desc.key = "other"  # type: ignore[misc]


def test_switch_types_tuple_has_six_entries() -> None:
    assert len(SWITCH_TYPES) == 6


def test_switch_types_all_have_key_and_translation_key() -> None:
    for desc in SWITCH_TYPES:
        assert desc.key
        assert desc.translation_key


# ===========================================================================
# PowerOnBehaviorSelect
# ===========================================================================


def test_power_on_behavior_select_unique_id_includes_host() -> None:
    coord = _make_coordinator()
    with patch(
        "custom_components.xenia_home.entity.XeniaEntity.__init__", return_value=None
    ):
        entity = PowerOnBehaviorSelect.__new__(PowerOnBehaviorSelect)
        entity.coordinator = coord
        entity.hass = MagicMock()
        PowerOnBehaviorSelect.__init__(entity, coord)
    assert "xenia.local" in entity._attr_unique_id


def test_power_on_behavior_select_options_match_constants() -> None:
    coord = _make_coordinator()
    with patch(
        "custom_components.xenia_home.entity.XeniaEntity.__init__", return_value=None
    ):
        entity = PowerOnBehaviorSelect.__new__(PowerOnBehaviorSelect)
        entity.coordinator = coord
        entity.hass = MagicMock()
        PowerOnBehaviorSelect.__init__(entity, coord)
    assert entity._attr_options == POWER_ON_BEHAVIOR_OPTIONS


def test_power_on_behavior_select_current_option_defaults_to_steam_off() -> None:
    coord = _make_coordinator(options={})
    with patch(
        "custom_components.xenia_home.entity.XeniaEntity.__init__", return_value=None
    ):
        entity = PowerOnBehaviorSelect.__new__(PowerOnBehaviorSelect)
        entity.coordinator = coord
        entity.hass = MagicMock()
        PowerOnBehaviorSelect.__init__(entity, coord)
    assert entity.current_option == DEFAULT_POWER_ON_BEHAVIOR


def test_power_on_behavior_select_current_option_returns_saved_value() -> None:
    coord = _make_coordinator(
        options={CONF_POWER_ON_BEHAVIOR: PowerOnBehavior.STEAM_ON}
    )
    with patch(
        "custom_components.xenia_home.entity.XeniaEntity.__init__", return_value=None
    ):
        entity = PowerOnBehaviorSelect.__new__(PowerOnBehaviorSelect)
        entity.coordinator = coord
        entity.hass = MagicMock()
        PowerOnBehaviorSelect.__init__(entity, coord)
    assert entity.current_option == PowerOnBehavior.STEAM_ON


@pytest.mark.asyncio
async def test_power_on_behavior_select_option_updates_config_entry() -> None:
    coord = _make_coordinator(options={})
    with patch(
        "custom_components.xenia_home.entity.XeniaEntity.__init__", return_value=None
    ):
        entity = PowerOnBehaviorSelect.__new__(PowerOnBehaviorSelect)
        entity.coordinator = coord
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()
        PowerOnBehaviorSelect.__init__(entity, coord)

    entity.hass.config_entries = MagicMock()
    entity.hass.config_entries.async_update_entry = MagicMock()

    await entity.async_select_option(PowerOnBehavior.STEAM_ON)

    entity.hass.config_entries.async_update_entry.assert_called_once()
    call_kwargs = entity.hass.config_entries.async_update_entry.call_args[1]
    assert call_kwargs["options"][CONF_POWER_ON_BEHAVIOR] == PowerOnBehavior.STEAM_ON


@pytest.mark.asyncio
async def test_power_on_behavior_select_invalid_option_does_nothing() -> None:
    coord = _make_coordinator(options={})
    with patch(
        "custom_components.xenia_home.entity.XeniaEntity.__init__", return_value=None
    ):
        entity = PowerOnBehaviorSelect.__new__(PowerOnBehaviorSelect)
        entity.coordinator = coord
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()
        PowerOnBehaviorSelect.__init__(entity, coord)

    entity.hass.config_entries = MagicMock()
    entity.hass.config_entries.async_update_entry = MagicMock()

    await entity.async_select_option("invalid_option")

    entity.hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.asyncio
async def test_power_on_behavior_select_calls_write_ha_state() -> None:
    coord = _make_coordinator(options={})
    with patch(
        "custom_components.xenia_home.entity.XeniaEntity.__init__", return_value=None
    ):
        entity = PowerOnBehaviorSelect.__new__(PowerOnBehaviorSelect)
        entity.coordinator = coord
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()
        PowerOnBehaviorSelect.__init__(entity, coord)

    entity.hass.config_entries = MagicMock()
    entity.hass.config_entries.async_update_entry = MagicMock()

    await entity.async_select_option(PowerOnBehavior.STEAM_OFF)
    entity.async_write_ha_state.assert_called_once()


# ===========================================================================
# ScriptSelect
# ===========================================================================


def test_script_select_unique_id_includes_domain_and_host() -> None:
    coord = _make_coordinator()
    with patch(
        "custom_components.xenia_home.entity.XeniaEntity.__init__", return_value=None
    ):
        entity = ScriptSelect.__new__(ScriptSelect)
        entity.coordinator = coord
        entity.hass = MagicMock()
        ScriptSelect.__init__(entity, coord)
    assert XENIA_DOMAIN in entity._attr_unique_id
    assert "xenia.local" in entity._attr_unique_id


def test_script_select_options_returns_script_titles() -> None:
    coord = _make_coordinator(scripts={0: "None", 1: "Espresso", 10: "MyShot"})
    with patch(
        "custom_components.xenia_home.entity.XeniaEntity.__init__", return_value=None
    ):
        entity = ScriptSelect.__new__(ScriptSelect)
        entity.coordinator = coord
        entity.hass = MagicMock()
        ScriptSelect.__init__(entity, coord)

    options = entity.options
    assert "None" in options
    assert "Espresso" in options
    assert "MyShot" in options


def test_script_select_current_option_none_when_no_selection() -> None:
    coord = _make_coordinator(scripts={1: "Espresso"})
    with patch(
        "custom_components.xenia_home.entity.XeniaEntity.__init__", return_value=None
    ):
        entity = ScriptSelect.__new__(ScriptSelect)
        entity.coordinator = coord
        entity.hass = MagicMock()
        ScriptSelect.__init__(entity, coord)

    coord.config_entry.runtime_data.config_coordinator.selected_script_id = None
    assert entity.current_option is None


def test_script_select_current_option_returns_title_for_selected_id() -> None:
    coord = _make_coordinator(scripts={1: "Espresso", 10: "MyShot"})
    coord.config_entry.runtime_data.config_coordinator.selected_script_id = 10
    with patch(
        "custom_components.xenia_home.entity.XeniaEntity.__init__", return_value=None
    ):
        entity = ScriptSelect.__new__(ScriptSelect)
        entity.coordinator = coord
        entity.hass = MagicMock()
        ScriptSelect.__init__(entity, coord)

    assert entity.current_option == "MyShot"


def test_script_select_current_option_none_for_unknown_id() -> None:
    coord = _make_coordinator(scripts={1: "Espresso"})
    coord.config_entry.runtime_data.config_coordinator.selected_script_id = 999
    with patch(
        "custom_components.xenia_home.entity.XeniaEntity.__init__", return_value=None
    ):
        entity = ScriptSelect.__new__(ScriptSelect)
        entity.coordinator = coord
        entity.hass = MagicMock()
        ScriptSelect.__init__(entity, coord)

    assert entity.current_option is None


@pytest.mark.asyncio
async def test_script_select_async_select_option_sets_script_id() -> None:
    coord = _make_coordinator(scripts={1: "Espresso", 10: "MyShot"})
    with patch(
        "custom_components.xenia_home.entity.XeniaEntity.__init__", return_value=None
    ):
        entity = ScriptSelect.__new__(ScriptSelect)
        entity.coordinator = coord
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()
        ScriptSelect.__init__(entity, coord)

    await entity.async_select_option("MyShot")

    assert coord.config_entry.runtime_data.config_coordinator.selected_script_id == 10


@pytest.mark.asyncio
async def test_script_select_async_select_option_unknown_title_does_not_crash() -> None:
    """Selecting a non-existent title should silently do nothing (no match in loop)."""
    coord = _make_coordinator(scripts={1: "Espresso"})
    with patch(
        "custom_components.xenia_home.entity.XeniaEntity.__init__", return_value=None
    ):
        entity = ScriptSelect.__new__(ScriptSelect)
        entity.coordinator = coord
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()
        ScriptSelect.__init__(entity, coord)

    # Should not raise
    await entity.async_select_option("NonExistent")


# ===========================================================================
# SwitchConfigSelect
# ===========================================================================


def test_switch_config_select_unique_id_includes_switch_key() -> None:
    coord = _make_coordinator()
    desc = SwitchDescription(
        key="SWITCH_SET_LEFT_LEFT_0", translation_key="switch_left_short"
    )
    with patch(
        "custom_components.xenia_home.entity.XeniaEntity.__init__", return_value=None
    ):
        entity = SwitchConfigSelect.__new__(SwitchConfigSelect)
        entity.coordinator = coord
        entity.hass = MagicMock()
        SwitchConfigSelect.__init__(entity, coord, desc)

    assert "SWITCH_SET_LEFT_LEFT_0" in entity._attr_unique_id
    assert "xenia.local" in entity._attr_unique_id


def test_switch_config_select_options_returns_script_titles() -> None:
    coord = _make_coordinator(scripts={0: "None", 1: "Espresso"})
    desc = SwitchDescription(key="SWITCH_SET_LEFT_LEFT_0", translation_key="t")
    with patch(
        "custom_components.xenia_home.entity.XeniaEntity.__init__", return_value=None
    ):
        entity = SwitchConfigSelect.__new__(SwitchConfigSelect)
        entity.coordinator = coord
        entity.hass = MagicMock()
        SwitchConfigSelect.__init__(entity, coord, desc)

    options = entity.options
    assert "None" in options
    assert "Espresso" in options


def test_switch_config_select_current_option_returns_assigned_script() -> None:
    coord = _make_coordinator(
        scripts={0: "None", 1: "Espresso"},
        switches={"SWITCH_SET_LEFT_LEFT_0": 1},
    )
    desc = SwitchDescription(key="SWITCH_SET_LEFT_LEFT_0", translation_key="t")
    with patch(
        "custom_components.xenia_home.entity.XeniaEntity.__init__", return_value=None
    ):
        entity = SwitchConfigSelect.__new__(SwitchConfigSelect)
        entity.coordinator = coord
        entity.hass = MagicMock()
        SwitchConfigSelect.__init__(entity, coord, desc)

    assert entity.current_option == "Espresso"


def test_switch_config_select_current_option_defaults_to_none_script() -> None:
    """If a switch is not in the switches dict, it should default to script ID 0 = 'None'."""
    coord = _make_coordinator(
        scripts={0: "None", 1: "Espresso"},
        switches={},
    )
    desc = SwitchDescription(key="SWITCH_NOT_PRESENT", translation_key="t")
    with patch(
        "custom_components.xenia_home.entity.XeniaEntity.__init__", return_value=None
    ):
        entity = SwitchConfigSelect.__new__(SwitchConfigSelect)
        entity.coordinator = coord
        entity.hass = MagicMock()
        SwitchConfigSelect.__init__(entity, coord, desc)

    assert entity.current_option == "None"


def test_switch_config_select_current_option_none_when_script_not_found() -> None:
    """If the script ID from the switch does not exist in scripts, return None."""
    coord = _make_coordinator(
        scripts={1: "Espresso"},
        switches={"SWITCH_SET_LEFT_LEFT_0": 999},
    )
    desc = SwitchDescription(key="SWITCH_SET_LEFT_LEFT_0", translation_key="t")
    with patch(
        "custom_components.xenia_home.entity.XeniaEntity.__init__", return_value=None
    ):
        entity = SwitchConfigSelect.__new__(SwitchConfigSelect)
        entity.coordinator = coord
        entity.hass = MagicMock()
        SwitchConfigSelect.__init__(entity, coord, desc)

    assert entity.current_option is None


@pytest.mark.asyncio
async def test_switch_config_select_async_select_option_calls_set_switch() -> None:
    coord = _make_coordinator(
        scripts={0: "None", 1: "Espresso", 10: "MyShot"},
        switches={"SWITCH_SET_LEFT_LEFT_0": 0},
    )
    coord.xenia = MagicMock()
    coord.xenia.set_switch = AsyncMock()

    desc = SwitchDescription(key="SWITCH_SET_LEFT_LEFT_0", translation_key="t")
    with patch(
        "custom_components.xenia_home.entity.XeniaEntity.__init__", return_value=None
    ):
        entity = SwitchConfigSelect.__new__(SwitchConfigSelect)
        entity.coordinator = coord
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()
        SwitchConfigSelect.__init__(entity, coord, desc)

    await entity.async_select_option("MyShot")

    coord.xenia.set_switch.assert_called_once_with("SWITCH_SET_LEFT_LEFT_0", 10)


@pytest.mark.asyncio
async def test_switch_config_select_async_select_option_unknown_defaults_to_zero() -> (
    None
):
    """If the selected title does not match any script, script_id defaults to 0."""
    coord = _make_coordinator(
        scripts={0: "None", 1: "Espresso"},
        switches={"SWITCH_SET_LEFT_LEFT_0": 1},
    )
    coord.xenia = MagicMock()
    coord.xenia.set_switch = AsyncMock()

    desc = SwitchDescription(key="SWITCH_SET_LEFT_LEFT_0", translation_key="t")
    with patch(
        "custom_components.xenia_home.entity.XeniaEntity.__init__", return_value=None
    ):
        entity = SwitchConfigSelect.__new__(SwitchConfigSelect)
        entity.coordinator = coord
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()
        SwitchConfigSelect.__init__(entity, coord, desc)

    await entity.async_select_option("NonExistent")

    coord.xenia.set_switch.assert_called_once_with("SWITCH_SET_LEFT_LEFT_0", 0)


@pytest.mark.asyncio
async def test_switch_config_select_async_select_option_refreshes_config() -> None:
    coord = _make_coordinator(
        scripts={0: "None", 1: "Espresso"},
        switches={"SWITCH_SET_LEFT_LEFT_0": 0},
    )
    coord.xenia = MagicMock()
    coord.xenia.set_switch = AsyncMock()

    desc = SwitchDescription(key="SWITCH_SET_LEFT_LEFT_0", translation_key="t")
    with patch(
        "custom_components.xenia_home.entity.XeniaEntity.__init__", return_value=None
    ):
        entity = SwitchConfigSelect.__new__(SwitchConfigSelect)
        entity.coordinator = coord
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()
        SwitchConfigSelect.__init__(entity, coord, desc)

    await entity.async_select_option("Espresso")

    coord.config_entry.runtime_data.config_coordinator.async_request_refresh.assert_called_once()
