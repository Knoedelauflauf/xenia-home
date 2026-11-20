"""Button platform for the Xenia espresso machine."""

from typing import override

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import XENIA_DOMAIN
from .coordinator import XeniaConfigEntry, XeniaDataUpdateCoordinator
from .entity import XeniaEntity
from .errors import async_write

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
        self._attr_unique_id = f"{self.machine_id}_execute_script"

    @override
    async def async_press(self) -> None:
        """Run the selected script."""
        script_id = self.runtime_data.selected_script_id
        if not script_id:
            raise ServiceValidationError(
                translation_domain=XENIA_DOMAIN, translation_key="no_script_selected"
            )
        await async_write(
            self.coordinator, self.coordinator.xenia.execute_script(script_id)
        )


class XeniaStopScriptButton(XeniaEntity, ButtonEntity):
    """Stop the running script."""

    _attr_translation_key = "stop_script"

    def __init__(self, coordinator: XeniaDataUpdateCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{self.machine_id}_stop_script"

    @override
    async def async_press(self) -> None:
        """Stop the running script."""
        await async_write(self.coordinator, self.coordinator.xenia.stop_script())
