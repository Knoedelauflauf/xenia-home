"""Tests for binary_sensor.py — water tank empty sensor."""

import pytest

# ===========================================================================
# Snapshot — covers unique_id, translation_key, device_class, icon, name
# ===========================================================================


async def test_binary_sensor_entities_snapshot(
    hass, init_integration, snapshot, entity_registry
):
    entity_ids = sorted(
        e.entity_id
        for e in entity_registry.entities.values()
        if e.platform == "xenia_home" and e.domain == "binary_sensor"
    )
    assert entity_ids, "no binary_sensor entities created"
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        registry_entry = entity_registry.async_get(entity_id)
        assert state == snapshot(name=f"{entity_id}-state")
        assert registry_entry == snapshot(name=f"{entity_id}-registry")


# ===========================================================================
# is_on logic — water tank level: 1=present (no problem), 2=empty (problem)
# ===========================================================================


@pytest.mark.parametrize(
    ("level", "expected_state"),
    [
        (1, "off"),  # water present
        (2, "on"),  # tank empty
        (0, "off"),  # unknown value, treat as not-empty
        (3, "off"),  # unknown value
        (99, "off"),  # unknown value
    ],
)
async def test_water_tank_state_for_level(
    hass,
    enable_custom_integrations,
    mock_xenia_api,
    mock_config_entry,
    level,
    expected_state,
):
    mock_xenia_api.set_overview_single(PU_SENS_WATER_TANK_LEVEL=level)
    mock_xenia_api.register()
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.xenia_espresso_machine_water_tank_empty")
    assert state is not None
    assert state.state == expected_state
