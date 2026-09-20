"""Select platform for Xenia espresso machine."""

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity
from homeassistant.const import CONF_HOST, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import POWER_ON_BEHAVIOR_OPTIONS, XENIA_DOMAIN
from .coordinator import XeniaConfigEntry, XeniaDataUpdateCoordinator
from .entity import XeniaEntity
from .errors import machine_write

PARALLEL_UPDATES = 1


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
    entities.extend(SwitchConfigSelect(coordinator, sd) for sd in SWITCH_TYPES)
    async_add_entities(entities)


class PowerOnBehaviorSelect(XeniaEntity, SelectEntity, RestoreEntity):
    """Select entity for power on behavior."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "power_on_behavior"
    _attr_options = POWER_ON_BEHAVIOR_OPTIONS

    def __init__(self, coordinator: XeniaDataUpdateCoordinator) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{XENIA_DOMAIN}_power_on_behavior_"
            f"{coordinator.config_entry.data[CONF_HOST]}"
        )

    @property
    def available(self) -> bool:
        """A local preference; an unavailable state would be restored as such."""
        return True

    async def async_added_to_hass(self) -> None:
        """Restore the last selected option."""
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state is not None and state.state in POWER_ON_BEHAVIOR_OPTIONS:
            self.runtime_data.power_on_behavior = state.state

    @property
    def current_option(self) -> str:
        """Return the current selected option."""
        return self.runtime_data.power_on_behavior

    async def async_select_option(self, option: str) -> None:
        """Handle option selection."""
        self.runtime_data.power_on_behavior = option
        self.async_write_ha_state()


class ScriptSelect(XeniaEntity, SelectEntity):
    """Select entity for choosing a script to execute."""

    _attr_translation_key = "script"

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
        script_id = next(
            (sid for sid, title in scripts.items() if title == option), None
        )
        if script_id is not None:
            config_coordinator.selected_script_id = script_id
        self.async_write_ha_state()


class SwitchConfigSelect(XeniaEntity, SelectEntity):
    """Select entity for configuring a physical switch."""

    _attr_entity_category = EntityCategory.CONFIG

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
        script_id = next((sid for sid, title in scripts.items() if title == option), 0)
        # Update the switch assignment
        async with machine_write():
            await self.coordinator.xenia.set_switch(self._switch_key, script_id)
        # Refresh config data
        await config_coordinator.async_request_refresh()
        self.async_write_ha_state()
