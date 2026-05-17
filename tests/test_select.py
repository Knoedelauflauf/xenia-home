"""Tests for select.py — power-on-behavior, script, and switch-config selects."""

from __future__ import annotations

import pytest

from custom_components.xenia_home.const import (
    CONF_POWER_ON_BEHAVIOR,
    PowerOnBehavior,
)


POBE = "select.xenia_espresso_machine_power_on_behavior"
SCRIPT = "select.xenia_espresso_machine_script"
SWITCH_LEFT_SHORT = "select.xenia_espresso_machine_left_switch_left_short"


async def test_select_entities_snapshot(
    hass, init_integration, snapshot, entity_registry
):
    entity_ids = sorted(
        e.entity_id
        for e in entity_registry.entities.values()
        if e.platform == "xenia_home" and e.domain == "select"
    )
    # 1 (power on behavior) + 1 (script) + 6 (switch configs) = 8
    assert len(entity_ids) == 8
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        registry_entry = entity_registry.async_get(entity_id)
        assert state == snapshot(name=f"{entity_id}-state")
        assert registry_entry == snapshot(name=f"{entity_id}-registry")


# ===========================================================================
# PowerOnBehaviorSelect
# ===========================================================================


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Bug #1: DEFAULT_POWER_ON_BEHAVIOR is a PowerOnBehavior enum instance; "
        "Python 3.11+ str(StrEnum) returns 'ClassName.MEMBER' not the value. "
        "Fix: set DEFAULT_POWER_ON_BEHAVIOR = PowerOnBehavior.STEAM_OFF.value in const.py. "
        "See docs/known-bugs.md#bug-1."
    ),
)
async def test_power_on_behavior_defaults_to_steam_off(hass, init_integration):
    state = hass.states.get(POBE)
    assert state.state == PowerOnBehavior.STEAM_OFF


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Bug #1: When CONF_POWER_ON_BEHAVIOR is set to a PowerOnBehavior enum "
        "instance (not a plain string), HA stores str(enum) = 'PowerOnBehavior.STEAM_ON'. "
        "Fix: store the .value string in options, or accept plain strings in config flow. "
        "See docs/known-bugs.md#bug-1."
    ),
)
async def test_power_on_behavior_reads_saved_option(
    hass,
    enable_custom_integrations,
    mock_xenia_api,
    mock_config_entry_factory_with_options,
):
    entry = mock_config_entry_factory_with_options(
        {CONF_POWER_ON_BEHAVIOR: PowerOnBehavior.STEAM_ON}
    )
    mock_xenia_api.register()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(POBE).state == PowerOnBehavior.STEAM_ON


async def test_power_on_behavior_select_updates_entry_options(hass, init_integration):
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": POBE, "option": PowerOnBehavior.STEAM_ON},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert init_integration.options[CONF_POWER_ON_BEHAVIOR] == PowerOnBehavior.STEAM_ON


async def test_power_on_behavior_invalid_option_raises(hass, init_integration):
    # HA's select platform validates options before forwarding to the entity
    with pytest.raises(Exception):
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": POBE, "option": "garbage"},
            blocking=True,
        )


# ===========================================================================
# ScriptSelect — selecting changes config_coordinator.selected_script_id
# ===========================================================================


async def test_script_select_options_include_builtin_and_user_scripts(
    hass, init_integration
):
    state = hass.states.get(SCRIPT)
    options = state.attributes.get("options", [])
    assert "None" in options
    assert "Espresso" in options
    assert "MyShot" in options  # from default SCRIPTS_PAYLOAD


async def test_script_select_sets_selected_script_id(hass, init_integration):
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": SCRIPT, "option": "MyShot"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert init_integration.runtime_data.config_coordinator.selected_script_id == 10


# ===========================================================================
# SwitchConfigSelect — selecting calls Xenia.set_switch
# ===========================================================================


async def test_switch_config_select_assigns_script_via_xenia(
    hass, init_integration, mock_xenia_api
):
    mock_xenia_api.expect_set_switch()
    # The set_switch implementation does a GET + POST to /switches.
    # The GET must return the current switches dict so it can be modified.
    mock_xenia_api._mock.get(
        mock_xenia_api._url("switches"),
        payload={"SWITCH_SET_LEFT_LEFT_0": 1, "SWITCH_SET_LEFT_LEFT_1": 2},
        repeat=True,
    )
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": SWITCH_LEFT_SHORT, "option": "MyShot"},
        blocking=True,
    )
    await hass.async_block_till_done()
    mock_xenia_api.assert_post_called_with("switches", "SWITCH_SET_LEFT_LEFT_0")
    mock_xenia_api.assert_post_called_with("switches", "10")
