"""Number platform for the Xenia espresso machine."""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
import logging
from typing import Any, Final

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
)
from homeassistant.const import CONF_HOST, EntityCategory, UnitOfMass, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_MANAGED_SCRIPT_ID,
    CONF_WEIGHT_MANAGEMENT_ENABLED,
    CONF_WEIGHT_MAX,
    CONF_WEIGHT_MIN,
    CONF_WEIGHT_STEP,
    DEFAULT_WEIGHT_MAX,
    DEFAULT_WEIGHT_MIN,
    DEFAULT_WEIGHT_STEP,
)
from .coordinator import (
    XeniaConfigCoordinator,
    XeniaConfigEntry,
    XeniaCoordinatorData,
    XeniaDataUpdateCoordinator,
)
from .entity import XeniaEntity, build_device_info
from .script_parser import get_weight_target, set_weight_target

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class XeniaEntityDescriptionMixinNumber:
    """Mixin adding `value_fn` and `set_fn` to a number description."""

    value_fn: Callable[[XeniaCoordinatorData], StateType]
    set_fn: Callable[[XeniaDataUpdateCoordinator, float], Coroutine[Any, Any, None]]


@dataclass(frozen=True, kw_only=True)
class XeniaNumberEntityDescription(
    NumberEntityDescription, XeniaEntityDescriptionMixinNumber
):
    """Number description with optional dynamic entity-category resolution."""

    entity_category_fn: (
        Callable[[XeniaCoordinatorData], EntityCategory | None] | None
    ) = None


NUMBER_TYPES: Final[tuple[XeniaNumberEntityDescription, ...]] = (
    XeniaNumberEntityDescription(
        key="brew_group_set_temperature",
        translation_key="brew_group_set_temperature",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda data: data.overview_single.bg_set_temp,
        set_fn=lambda coordinator, v: coordinator.xenia.set_bg_set_temp(v),
        native_min_value=60,
        native_max_value=96,
        native_step=0.5,
    ),
    XeniaNumberEntityDescription(
        key="brew_boiler_set_temperature",
        translation_key="brew_boiler_set_temperature",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda data: data.overview_single.bb_set_temp,
        set_fn=lambda coordinator, v: coordinator.xenia.set_bb_set_temp(v),
        native_min_value=60,
        native_max_value=96,
        native_step=0.5,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: XeniaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Xenia number entities (setpoints and weight target)."""
    coordinator = entry.runtime_data.coordinator
    entities: list[NumberEntity] = [
        XeniaNumber(coordinator, description) for description in NUMBER_TYPES
    ]

    if entry.options.get(CONF_WEIGHT_MANAGEMENT_ENABLED):
        config_coordinator = entry.runtime_data.config_coordinator
        entities.append(XeniaWeightNumber(config_coordinator))

    async_add_entities(entities)


class XeniaNumber(XeniaEntity, NumberEntity):
    """A live number (e.g. brew-group setpoint) backed by `value_fn`/`set_fn`."""

    def __init__(
        self,
        coordinator: XeniaDataUpdateCoordinator,
        entity_description: XeniaNumberEntityDescription,
    ) -> None:
        """Initialize the live-number entity."""
        super().__init__(coordinator)
        self.entity_description: XeniaNumberEntityDescription = entity_description
        self._attr_unique_id = (
            f"{coordinator.config_entry.data[CONF_HOST]}_{entity_description.key}"
        )
        self._attr_native_min_value = entity_description.native_min_value or 0.0
        self._attr_native_max_value = entity_description.native_max_value or 100.0
        self._attr_native_step = entity_description.native_step or 1.0

    @property
    def native_value(self) -> float | None:
        """Return the current native value from the coordinator data."""
        return self.entity_description.value_fn(self.coordinator.data)  # type: ignore[return-value]

    @property
    def entity_category(self) -> EntityCategory | None:
        """Resolve the entity category dynamically if `entity_category_fn` is set."""
        if self.entity_description.entity_category_fn is not None:
            return self.entity_description.entity_category_fn(self.coordinator.data)
        return super().entity_category

    async def async_set_native_value(self, value: float) -> None:
        """Push a new value to the machine and trigger a refresh."""
        try:
            await self.entity_description.set_fn(self.coordinator, float(value))
        finally:
            await self.coordinator.async_request_refresh()


class XeniaWeightNumber(CoordinatorEntity[XeniaConfigCoordinator], NumberEntity):
    """Number entity for the managed script weight target."""

    _attr_has_entity_name = True
    _attr_translation_key = "script_weight_target"
    _attr_device_class = NumberDeviceClass.WEIGHT
    _attr_native_unit_of_measurement = UnitOfMass.GRAMS
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: XeniaConfigCoordinator) -> None:
        """Initialize the weight-target entity."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.config_entry.data[CONF_HOST]}_script_weight_target"
        )
        options = coordinator.config_entry.options
        self._attr_native_min_value = options.get(CONF_WEIGHT_MIN, DEFAULT_WEIGHT_MIN)
        self._attr_native_max_value = options.get(CONF_WEIGHT_MAX, DEFAULT_WEIGHT_MAX)
        self._attr_native_step = options.get(CONF_WEIGHT_STEP, DEFAULT_WEIGHT_STEP)

    @property
    def native_value(self) -> float | None:
        """Return the weight target parsed from the managed script."""
        instruction = self.coordinator.data.managed_script_instruction
        if instruction is None:
            return None
        return get_weight_target(instruction)

    @property
    def available(self) -> bool:
        """Available only when weight management is enabled and a script is known."""
        options = self.coordinator.config_entry.options
        if not options.get(CONF_WEIGHT_MANAGEMENT_ENABLED):
            return False
        return self.coordinator.data.managed_script_instruction is not None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information about this Xenia espresso machine."""
        host = self.coordinator.config_entry.data[CONF_HOST]
        machine = self.coordinator.data.machine
        return build_device_info(host, machine)

    async def async_set_native_value(self, value: float) -> None:
        """Rewrite the weight-target command in the managed script on the machine."""
        options = self.coordinator.config_entry.options
        script_id = options.get(CONF_MANAGED_SCRIPT_ID)
        if script_id is None:
            return
        # Read fresh from machine to avoid stale data
        script_data = await self.coordinator.xenia.read_script(int(script_id))
        instruction = script_data.get("Content")
        name = script_data.get("Title")
        if instruction is None or name is None:
            return
        new_instruction = set_weight_target(instruction, value)
        await self.coordinator.xenia.update_script(
            int(script_id), name, new_instruction
        )
        await self.coordinator.async_request_refresh()
