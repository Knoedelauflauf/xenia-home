"""Tests for select.py — power-on-behavior, script, and switch-config selects."""

from datetime import timedelta

from homeassistant.core import State
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed,
    mock_restore_cache,
)

from custom_components.xenia_home.const import CONF_POWER_ON_BEHAVIOR, PowerOnBehavior

POWER_ON_BEHAVIOR = "select.xenia_espresso_machine_power_on_behavior"
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


async def test_power_on_behavior_defaults_to_steam_off(hass, init_integration):
    state = hass.states.get(POWER_ON_BEHAVIOR)
    assert state.state == PowerOnBehavior.STEAM_OFF.value


async def test_power_on_behavior_option_is_migrated_and_removed(
    hass,
    enable_custom_integrations,
    mock_xenia_api,
    mock_config_entry_factory_with_options,
):
    entry = mock_config_entry_factory_with_options(
        {CONF_POWER_ON_BEHAVIOR: PowerOnBehavior.STEAM_ON.value}
    )
    mock_xenia_api.register()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(POWER_ON_BEHAVIOR).state == PowerOnBehavior.STEAM_ON.value
    assert CONF_POWER_ON_BEHAVIOR not in entry.options


async def test_power_on_behavior_select_does_not_reload_the_entry(
    hass, init_integration
):
    runtime_data = init_integration.runtime_data
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": POWER_ON_BEHAVIOR, "option": PowerOnBehavior.STEAM_ON},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get(POWER_ON_BEHAVIOR).state == PowerOnBehavior.STEAM_ON.value
    assert init_integration.runtime_data is runtime_data


async def test_power_on_behavior_is_restored_after_restart(
    hass, enable_custom_integrations, mock_xenia_api, mock_config_entry
):
    mock_restore_cache(
        hass, (State(POWER_ON_BEHAVIOR, PowerOnBehavior.STEAM_ON.value),)
    )
    mock_xenia_api.register()
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(POWER_ON_BEHAVIOR).state == PowerOnBehavior.STEAM_ON.value


async def test_power_on_behavior_stays_available_without_machine(
    hass, init_integration
):
    """The select is a local preference; an unreachable machine must not
    make it unavailable, or a restart would store and restore that state."""
    coordinator = init_integration.runtime_data.coordinator
    coordinator.last_update_success = False
    coordinator.async_update_listeners()
    await hass.async_block_till_done()
    assert hass.states.get(POWER_ON_BEHAVIOR).state == PowerOnBehavior.STEAM_OFF.value


async def test_power_on_behavior_survives_reload(hass, init_integration):
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": POWER_ON_BEHAVIOR, "option": PowerOnBehavior.STEAM_ON},
        blocking=True,
    )
    await hass.config_entries.async_reload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(POWER_ON_BEHAVIOR).state == PowerOnBehavior.STEAM_ON.value


async def test_power_on_behavior_invalid_option_raises(hass, init_integration):
    # HA's select platform validates options before forwarding to the entity
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": POWER_ON_BEHAVIOR, "option": "garbage"},
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


async def test_script_rename_reaches_the_select_without_a_reload(
    hass, init_integration, mock_xenia_api, freezer
):
    mock_xenia_api.set_scripts({10: "MyShot renamed", 20: "Lungo"})
    freezer.tick(timedelta(hours=1, seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    options = hass.states.get(SCRIPT).attributes["options"]
    assert "MyShot renamed" in options
    assert "MyShot" not in options


async def test_switch_config_select_raises_translated_error_when_machine_refuses(
    hass, init_integration, mock_xenia_api
):
    mock_xenia_api.fail_post("switches")
    with pytest.raises(HomeAssistantError) as exc_info:
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": SWITCH_LEFT_SHORT, "option": "MyShot"},
            blocking=True,
        )
    assert exc_info.value.translation_key == "write_failed"
