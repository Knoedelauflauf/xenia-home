"""Button platform for the Xenia espresso machine."""

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import XENIA_DOMAIN
from .coordinator import XeniaConfigEntry, XeniaDataUpdateCoordinator
from .entity import XeniaEntity
from .errors import machine_write

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: XeniaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the script buttons."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [XeniaExecuteScriptButton(coordinator), XeniaStopScriptButton(coordinator)]
    )


class XeniaExecuteScriptButton(XeniaEntity, ButtonEntity):
    """Run the script picked in the script select."""

    _attr_translation_key = "execute_script"

    def __init__(self, coordinator: XeniaDataUpdateCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{XENIA_DOMAIN}_execute_script_{self.machine_id}"

    async def async_press(self) -> None:
        """Run the selected script, if one is selected."""
        script_id = self.runtime_data.config_coordinator.selected_script_id
        if script_id:
            async with machine_write():
                await self.coordinator.xenia.execute_script(script_id)


class XeniaStopScriptButton(XeniaEntity, ButtonEntity):
    """Stop the running script."""

    _attr_translation_key = "stop_script"

    def __init__(self, coordinator: XeniaDataUpdateCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{XENIA_DOMAIN}_stop_script_{self.machine_id}"

    async def async_press(self) -> None:
        """Stop the running script."""
        async with machine_write():
            await self.coordinator.xenia.stop_script()
