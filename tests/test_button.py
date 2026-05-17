"""Tests for button.py — execute script button."""

from __future__ import annotations

import pytest


BUTTON_ENTITY_ID = "button.xenia_espresso_machine_execute_script"


async def test_button_entities_snapshot(
    hass, init_integration, snapshot, entity_registry
):
    entity_ids = sorted(
        e.entity_id
        for e in entity_registry.entities.values()
        if e.platform == "xenia_home" and e.domain == "button"
    )
    assert entity_ids
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        registry_entry = entity_registry.async_get(entity_id)
        assert state == snapshot(name=f"{entity_id}-state")
        assert registry_entry == snapshot(name=f"{entity_id}-registry")


# ===========================================================================
# press behavior depends on selected_script_id, which lives on
# config_coordinator. We modify it directly after the integration is up.
# ===========================================================================


async def _press_button(hass) -> None:
    await hass.services.async_call(
        "button", "press", {"entity_id": BUTTON_ENTITY_ID}, blocking=True
    )
    await hass.async_block_till_done()


async def test_button_press_executes_selected_script(
    hass, init_integration, mock_xenia_api
):
    mock_xenia_api.expect_execute_script()
    init_integration.runtime_data.config_coordinator.selected_script_id = 10
    await _press_button(hass)
    mock_xenia_api.assert_post_called_with("scripts/execute", "10")


@pytest.mark.parametrize("script_id", [None, 0, -1])
async def test_button_press_noop_for_invalid_script_id(
    hass, init_integration, mock_xenia_api, script_id
):
    mock_xenia_api.expect_execute_script()
    init_integration.runtime_data.config_coordinator.selected_script_id = script_id
    await _press_button(hass)
    assert mock_xenia_api.post_count("scripts/execute") == 0


async def test_button_press_executes_builtin_script_id_one(
    hass, init_integration, mock_xenia_api
):
    mock_xenia_api.expect_execute_script()
    init_integration.runtime_data.config_coordinator.selected_script_id = 1
    await _press_button(hass)
    mock_xenia_api.assert_post_called_with("scripts/execute", "1")
