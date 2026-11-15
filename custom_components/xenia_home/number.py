"""Number platform for the Xenia espresso machine."""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any, Final, override

from homeassistant.components.number import (
    DOMAIN as NUMBER_DOMAIN,
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
)
from homeassistant.const import EntityCategory, UnitOfMass, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
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
    XENIA_DOMAIN,
)
from .coordinator import (
    XeniaConfigCoordinator,
    XeniaConfigEntry,
    XeniaCoordinatorData,
    XeniaDataUpdateCoordinator,
)
from .entity import XeniaEntity, build_device_info, machine_id
from .errors import machine_write
from .script_parser import get_weight_target, set_weight_target
from .xenia import Xenia

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class XeniaNumberEntityDescription(NumberEntityDescription):
    """Describes a setpoint of the machine."""

    value_fn: Callable[[XeniaCoordinatorData], float | None]
    set_fn: Callable[[Xenia, float], Coroutine[Any, Any, None]]


NUMBER_TYPES: Final[tuple[XeniaNumberEntityDescription, ...]] = (
    XeniaNumberEntityDescription(
        key="brew_group_set_temperature",
        translation_key="brew_group_set_temperature",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda data: data.overview_single.bg_set_temp,
        set_fn=Xenia.set_bg_set_temp,
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
        set_fn=Xenia.set_bb_set_temp,
        native_min_value=60,
        native_max_value=96,
        native_step=0.5,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: XeniaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the setpoints and, with weight management, the weight target."""
    coordinator = entry.runtime_data.coordinator
    entities: list[NumberEntity] = [
        XeniaNumber(coordinator, description) for description in NUMBER_TYPES
    ]

    weight_unique_id = f"{machine_id(entry)}_script_weight_target"
    if entry.options.get(CONF_WEIGHT_MANAGEMENT_ENABLED):
        entities.append(
            XeniaWeightNumber(entry.runtime_data.config_coordinator, weight_unique_id)
        )
    else:
        registry = er.async_get(hass)
        if entity_id := registry.async_get_entity_id(
            NUMBER_DOMAIN, XENIA_DOMAIN, weight_unique_id
        ):
            registry.async_remove(entity_id)

    async_add_entities(entities)


class XeniaNumber(XeniaEntity, NumberEntity):
    """Setpoint of the machine."""

    entity_description: XeniaNumberEntityDescription

    def __init__(
        self,
        coordinator: XeniaDataUpdateCoordinator,
        entity_description: XeniaNumberEntityDescription,
    ) -> None:
        """Initialize the setpoint."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        self._attr_unique_id = f"{self.machine_id}_{entity_description.key}"

    @property
    @override
    def native_value(self) -> float | None:
        """Return the setpoint."""
        return self.entity_description.value_fn(self.coordinator.data)

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Write the setpoint, then poll the machine even if the write failed."""
        try:
            async with machine_write():
                await self.entity_description.set_fn(self.coordinator.xenia, value)
        finally:
            await self.coordinator.async_request_refresh()


class XeniaWeightNumber(CoordinatorEntity[XeniaConfigCoordinator], NumberEntity):
    """Weight target of the managed script."""

    _attr_has_entity_name = True
    _attr_translation_key = "script_weight_target"
    _attr_device_class = NumberDeviceClass.WEIGHT
    _attr_native_unit_of_measurement = UnitOfMass.GRAMS
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: XeniaConfigCoordinator, unique_id: str) -> None:
        """Initialize the weight target."""
        super().__init__(coordinator)
        self._attr_unique_id = unique_id
        options = coordinator.config_entry.options
        self._attr_native_min_value = options.get(CONF_WEIGHT_MIN, DEFAULT_WEIGHT_MIN)
        self._attr_native_max_value = options.get(CONF_WEIGHT_MAX, DEFAULT_WEIGHT_MAX)
        self._attr_native_step = options.get(CONF_WEIGHT_STEP, DEFAULT_WEIGHT_STEP)

    @property
    @override
    def native_value(self) -> float | None:
        """Return the weight target parsed from the managed script."""
        instruction = self.coordinator.data.managed_script_instruction
        if instruction is None:
            return None
        try:
            return get_weight_target(instruction)
        except ValueError:
            return None

    @property
    @override
    def available(self) -> bool:
        """Return whether the managed script could be read."""
        return (
            super().available
            and self.coordinator.data.managed_script_instruction is not None
        )

    @property
    @override
    def device_info(self) -> DeviceInfo:
        """Return the device info of the machine."""
        return build_device_info(
            self.coordinator.config_entry, self.coordinator.data.machine
        )

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Rewrite the weight target in the managed script on the machine."""
        script_id = self.coordinator.config_entry.options[CONF_MANAGED_SCRIPT_ID]
        async with machine_write():
            script = await self.coordinator.xenia.read_script(script_id)
        if not script.get("Content"):
            raise HomeAssistantError(
                translation_domain=XENIA_DOMAIN,
                translation_key="managed_script_missing",
                translation_placeholders={"script_id": str(script_id)},
            )
        try:
            instruction = set_weight_target(script["Content"], value)
        except ValueError as err:
            raise HomeAssistantError(
                translation_domain=XENIA_DOMAIN,
                translation_key="managed_script_unreadable",
                translation_placeholders={"script_id": str(script_id)},
            ) from err
        try:
            async with machine_write():
                await self.coordinator.xenia.update_script(
                    script_id, script.get("Title", ""), instruction
                )
        finally:
            await self.coordinator.async_request_refresh()
