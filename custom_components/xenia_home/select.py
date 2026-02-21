"""Select platform for Xenia espresso machine."""

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_POWER_ON_BEHAVIOR,
    DEFAULT_POWER_ON_BEHAVIOR,
    POWER_ON_BEHAVIOR_OPTIONS,
    XENIA_DOMAIN,
)
from .coordinator import XeniaConfigEntry, XeniaDataUpdateCoordinator
from .entity import XeniaEntity


@dataclass(frozen=True, kw_only=True)
class SwitchDescription:
    """Description of a physical switch on the machine."""

    key: str
    translation_key: str


SWITCH_TYPES: tuple[SwitchDescription, ...] = (
    SwitchDescription(
        key="SWITCH_SET_LEFT_LEFT_0",
        translation_key="switch_left_short",
    ),
    SwitchDescription(
        key="SWITCH_SET_LEFT_LEFT_1",
        translation_key="switch_left_long",
    ),
    SwitchDescription(
        key="SWITCH_SET_RIGHT_LEFT_0",
        translation_key="switch_right_left_short",
    ),
    SwitchDescription(
        key="SWITCH_SET_RIGHT_LEFT_1",
        translation_key="switch_right_left_long",
    ),
    SwitchDescription(
        key="SWITCH_SET_RIGHT_RIGHT_0",
        translation_key="switch_right_right_short",
    ),
    SwitchDescription(
        key="SWITCH_SET_RIGHT_RIGHT_1",
        translation_key="switch_right_right_long",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: XeniaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Xenia select entities."""
    coordinator = entry.runtime_data.coordinator
    entities: list[SelectEntity] = [
        PowerOnBehaviorSelect(coordinator),
        ScriptSelect(coordinator),
    ]
    for switch_desc in SWITCH_TYPES:
        entities.append(SwitchConfigSelect(coordinator, switch_desc))
    async_add_entities(entities)


class PowerOnBehaviorSelect(XeniaEntity, SelectEntity):
    """Select entity for power on behavior."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: XeniaDataUpdateCoordinator) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "power_on_behavior"
        self._attr_unique_id = (
            f"{XENIA_DOMAIN}_power_on_behavior_"
            f"{coordinator.config_entry.data[CONF_HOST]}"
        )
        self._attr_options = POWER_ON_BEHAVIOR_OPTIONS

    @property
    def current_option(self) -> str:
        """Return the current selected option."""
        return self.coordinator.config_entry.options.get(
            CONF_POWER_ON_BEHAVIOR, DEFAULT_POWER_ON_BEHAVIOR
        )

    async def async_select_option(self, option: str) -> None:
        """Handle option selection."""
        if option not in POWER_ON_BEHAVIOR_OPTIONS:
            return
        new_opts = dict(self.coordinator.config_entry.options)
        new_opts[CONF_POWER_ON_BEHAVIOR] = option
        self.hass.config_entries.async_update_entry(
            self.coordinator.config_entry, options=new_opts
        )
        self.async_write_ha_state()


class ScriptSelect(XeniaEntity, SelectEntity):
    """Select entity for choosing a script to execute."""

    _attr_translation_key = "script"
    _attr_icon = "mdi:script-text"

    def __init__(self, coordinator: XeniaDataUpdateCoordinator) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{XENIA_DOMAIN}_script_{coordinator.config_entry.data[CONF_HOST]}"
        )

    @property
    def options(self) -> list[str]:
        """Return the list of available scripts."""
        scripts = self.runtime_data.config_coordinator.data.scripts
        return list(scripts.values())

    @property
    def current_option(self) -> str | None:
        """Return the currently selected script."""
        config_coordinator = self.runtime_data.config_coordinator
        script_id = config_coordinator.selected_script_id
        if script_id is None:
            return None
        return config_coordinator.data.scripts.get(script_id)

    async def async_select_option(self, option: str) -> None:
        """Handle script selection."""
        config_coordinator = self.runtime_data.config_coordinator
        scripts = config_coordinator.data.scripts
        # Find script ID by title
        for script_id, title in scripts.items():
            if title == option:
                config_coordinator.selected_script_id = script_id
                break
        self.async_write_ha_state()


class SwitchConfigSelect(XeniaEntity, SelectEntity):
    """Select entity for configuring a physical switch."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:gesture-tap-button"

    def __init__(
        self,
        coordinator: XeniaDataUpdateCoordinator,
        description: SwitchDescription,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._switch_key = description.key
        self._attr_translation_key = description.translation_key
        self._attr_unique_id = f"{XENIA_DOMAIN}_{description.key}_{coordinator.config_entry.data[CONF_HOST]}"

    @property
    def options(self) -> list[str]:
        """Return the list of available scripts."""
        scripts = self.runtime_data.config_coordinator.data.scripts
        return list(scripts.values())

    @property
    def current_option(self) -> str | None:
        """Return the currently assigned script."""
        config_coordinator = self.runtime_data.config_coordinator
        switches = config_coordinator.data.switches
        script_id = switches.get(self._switch_key, 0)
        return config_coordinator.data.scripts.get(script_id)

    async def async_select_option(self, option: str) -> None:
        """Handle switch script assignment."""
        config_coordinator = self.runtime_data.config_coordinator
        scripts = config_coordinator.data.scripts
        # Find script ID by title
        script_id = 0
        for sid, title in scripts.items():
            if title == option:
                script_id = sid
                break
        # Update the switch assignment
        await self.coordinator.xenia.set_switch(self._switch_key, script_id)
        # Refresh config data
        await config_coordinator.async_request_refresh()
        self.async_write_ha_state()
