from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any, Final

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
)
from homeassistant.const import CONF_HOST, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import (
    XeniaConfigEntry,
    XeniaCoordinatorData,
    XeniaDataUpdateCoordinator,
)
from .entity import XeniaEntity


@dataclass(frozen=True, kw_only=True)
class XeniaEntityDescriptionMixinNumber:
    value_fn: Callable[[XeniaCoordinatorData], StateType]
    set_fn: Callable[[XeniaDataUpdateCoordinator, float], Coroutine[Any, Any, None]]


@dataclass(frozen=True, kw_only=True)
class XeniaNumberEntityDescription(
    NumberEntityDescription, XeniaEntityDescriptionMixinNumber
):
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
):
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        XeniaNumber(coordinator, description) for description in NUMBER_TYPES
    )


class XeniaNumber(XeniaEntity, NumberEntity):
    def __init__(
        self,
        coordinator: XeniaDataUpdateCoordinator,
        entity_description: XeniaNumberEntityDescription,
    ) -> None:
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
        return self.entity_description.value_fn(self.coordinator.data)  # type: ignore[return-value]

    @property
    def entity_category(self) -> EntityCategory | None:
        if self.entity_description.entity_category_fn is not None:
            return self.entity_description.entity_category_fn(self.coordinator.data)
        return super().entity_category

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.entity_description.set_fn(self.coordinator, float(value))
        finally:
            await self.coordinator.async_request_refresh()
