"""Select platform for the Xenia espresso machine."""

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import POWER_ON_BEHAVIOR_OPTIONS, PowerOnBehavior
from .coordinator import XeniaConfigEntry, XeniaDataUpdateCoordinator
from .entity import XeniaEntity
from .errors import machine_write

PARALLEL_UPDATES = 1


SWITCH_TYPES: tuple[SelectEntityDescription, ...] = (
    SelectEntityDescription(
        key="SWITCH_SET_LEFT_LEFT_0", translation_key="switch_left_short"
    ),
    SelectEntityDescription(
        key="SWITCH_SET_LEFT_LEFT_1", translation_key="switch_left_long"
    ),
    SelectEntityDescription(
        key="SWITCH_SET_RIGHT_LEFT_0", translation_key="switch_right_left_short"
    ),
    SelectEntityDescription(
        key="SWITCH_SET_RIGHT_LEFT_1", translation_key="switch_right_left_long"
    ),
    SelectEntityDescription(
        key="SWITCH_SET_RIGHT_RIGHT_0", translation_key="switch_right_right_short"
    ),
    SelectEntityDescription(
        key="SWITCH_SET_RIGHT_RIGHT_1", translation_key="switch_right_right_long"
    ),
)


def _script_id(scripts: dict[int, str], title: str) -> int:
    # Home Assistant only passes options the select offers.
    return next(sid for sid, name in scripts.items() if name == title)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: XeniaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the power on behavior, script and switch selects."""
    coordinator = entry.runtime_data.coordinator
    entities: list[SelectEntity] = [
        PowerOnBehaviorSelect(coordinator),
        ScriptSelect(coordinator),
    ]
    entities.extend(SwitchConfigSelect(coordinator, sd) for sd in SWITCH_TYPES)
    async_add_entities(entities)


class PowerOnBehaviorSelect(XeniaEntity, SelectEntity, RestoreEntity):
    """Whether the steam boiler turns on with the machine; kept by Home Assistant."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "power_on_behavior"
    _attr_options = POWER_ON_BEHAVIOR_OPTIONS

    def __init__(self, coordinator: XeniaDataUpdateCoordinator) -> None:
        """Initialize the select."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{self.machine_id}_power_on_behavior"

    @property
    def available(self) -> bool:
        """A local preference; an unavailable state would be restored as such."""
        return True

    async def async_added_to_hass(self) -> None:
        """Restore the last selected option."""
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state is not None and state.state in POWER_ON_BEHAVIOR_OPTIONS:
            self.runtime_data.power_on_behavior = PowerOnBehavior(state.state)

    @callback
    def async_entity_id_changed(self, old_entity_id: str) -> None:
        """Keep the entity when its entity_id changes; nothing is keyed on it."""
        # Called from Home Assistant 2026.11 on, which added the hook.
        super().async_entity_id_changed(old_entity_id)  # type: ignore[misc]

    @property
    def current_option(self) -> str:
        """Return the power on behavior."""
        return self.runtime_data.power_on_behavior

    async def async_select_option(self, option: str) -> None:
        """Set the power on behavior."""
        self.runtime_data.power_on_behavior = PowerOnBehavior(option)
        self.async_write_ha_state()


class ScriptSelect(XeniaEntity, SelectEntity):
    """The script the execute button runs."""

    _attr_translation_key = "script"

    def __init__(self, coordinator: XeniaDataUpdateCoordinator) -> None:
        """Initialize the select."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{self.machine_id}_script"

    @property
    def options(self) -> list[str]:
        """Return the script titles."""
        return list(self.runtime_data.config_coordinator.data.scripts.values())

    @property
    def current_option(self) -> str | None:
        """Return the selected script."""
        script_id = self.runtime_data.selected_script_id
        if script_id is None:
            return None
        return self.runtime_data.config_coordinator.data.scripts.get(script_id)

    async def async_select_option(self, option: str) -> None:
        """Select a script."""
        self.runtime_data.selected_script_id = _script_id(
            self.runtime_data.config_coordinator.data.scripts, option
        )
        self.async_write_ha_state()


class SwitchConfigSelect(XeniaEntity, SelectEntity):
    """The script a switch on the machine runs."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: XeniaDataUpdateCoordinator,
        description: SelectEntityDescription,
    ) -> None:
        """Initialize the select."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{self.machine_id}_{description.key}"

    @property
    def options(self) -> list[str]:
        """Return the script titles."""
        return list(self.runtime_data.config_coordinator.data.scripts.values())

    @property
    def current_option(self) -> str | None:
        """Return the assigned script."""
        data = self.runtime_data.config_coordinator.data
        return data.scripts.get(data.switches.get(self.entity_description.key, 0))

    async def async_select_option(self, option: str) -> None:
        """Assign a script to the switch."""
        config_coordinator = self.runtime_data.config_coordinator
        async with machine_write():
            await self.coordinator.xenia.set_switch(
                self.entity_description.key,
                _script_id(config_coordinator.data.scripts, option),
            )
        await config_coordinator.async_request_refresh()
        self.async_write_ha_state()
