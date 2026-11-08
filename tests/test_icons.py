"""Tests for the icon translations."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.icon import async_get_icons
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xenia_home.const import XENIA_DOMAIN


async def test_entities_without_device_class_have_an_icon(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    init_integration: MockConfigEntry,
) -> None:
    """Every entity without a device class has an icon."""
    icons = (await async_get_icons(hass, "entity", [XENIA_DOMAIN]))[XENIA_DOMAIN]
    missing = [
        entry.entity_id
        for entry in er.async_entries_for_config_entry(
            entity_registry, init_integration.entry_id
        )
        if entry.original_device_class is None
        and entry.translation_key not in icons.get(entry.domain, {})
    ]
    assert missing == []


async def test_state_icons_use_real_states(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """State icons only name states the entities can have."""
    icons = (await async_get_icons(hass, "entity", [XENIA_DOMAIN]))[XENIA_DOMAIN]
    status = hass.states.get("sensor.xenia_espresso_machine_status")
    assert set(icons["sensor"]["status"]["state"]) <= set(status.attributes["options"])
    assert set(icons["binary_sensor"]["water_tank_empty"]["state"]) <= {"on", "off"}
