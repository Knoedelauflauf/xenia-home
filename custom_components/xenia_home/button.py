"""Button platform for Xenia espresso machine."""

from homeassistant.components.button import ButtonEntity
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import XENIA_DOMAIN
from .coordinator import XeniaConfigEntry, XeniaDataUpdateCoordinator
from .entity import XeniaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: XeniaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Xenia button entities."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities([XeniaExecuteScriptButton(coordinator)])


class XeniaExecuteScriptButton(XeniaEntity, ButtonEntity):
    """Button to execute the selected script."""

    _attr_translation_key = "execute_script"
    _attr_icon = "mdi:play"

    def __init__(self, coordinator: XeniaDataUpdateCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{XENIA_DOMAIN}_execute_script_"
            f"{coordinator.config_entry.data[CONF_HOST]}"
        )

    async def async_press(self) -> None:
        """Execute the selected script."""
        config_coordinator = self.runtime_data.config_coordinator
        selected_script_id = config_coordinator.selected_script_id
        if selected_script_id is not None and selected_script_id > 0:
            await self.coordinator.xenia.execute_script(selected_script_id)
