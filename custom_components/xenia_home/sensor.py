from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONF_HOST,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfEnergy,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
)
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
class XeniaEntityDescriptionMixinSensor:
    value_fn: Callable[[XeniaCoordinatorData], StateType]


@dataclass(frozen=True, kw_only=True)
class XeniaSensorEntityDescription(
    SensorEntityDescription, XeniaEntityDescriptionMixinSensor
):
    entity_category_fn: (
        Callable[[XeniaCoordinatorData], EntityCategory | None] | None
    ) = None


SENSOR_TYPES: Final[tuple[XeniaSensorEntityDescription, ...]] = (
    XeniaSensorEntityDescription(
        key="brew_group_temperature",
        translation_key="brew_group_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
        value_fn=lambda data: data.overview.bg_sens_temp_a,
    ),
    XeniaSensorEntityDescription(
        key="brew_boiler_temperature",
        translation_key="brew_boiler_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-water",
        value_fn=lambda data: data.overview.bb_sens_temp_a,
    ),
    XeniaSensorEntityDescription(
        key="pump_pressure",
        translation_key="pump_pressure",
        native_unit_of_measurement=UnitOfPressure.BAR,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gauge",
        value_fn=lambda data: data.overview.pu_sens_press,
    ),
    XeniaSensorEntityDescription(
        key="steam_boiler_pressure",
        translation_key="steam_boiler_pressure",
        native_unit_of_measurement=UnitOfPressure.BAR,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gauge-full",
        value_fn=lambda data: data.overview.sb_sens_press,
    ),
    XeniaSensorEntityDescription(
        key="electric_current",
        translation_key="electric_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:current-ac",
        value_fn=lambda data: data.overview.ma_cur_pwr,
    ),
    XeniaSensorEntityDescription(
        key="total_energy",
        translation_key="total_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:lightning-bolt",
        value_fn=lambda data: data.overview.ma_energy_total_kwh,
    ),
    XeniaSensorEntityDescription(
        key="extractions",
        translation_key="extractions",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:coffee-to-go",
        value_fn=lambda data: data.overview.ma_extractions,
    ),
    XeniaSensorEntityDescription(
        key="operating_hours",
        translation_key="operating_hours",
        native_unit_of_measurement=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:clock-outline",
        value_fn=lambda data: data.overview.ma_operating_hours / 60,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: XeniaConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        XeniaSensor(coordinator, description) for description in SENSOR_TYPES
    )


class XeniaSensor(XeniaEntity, SensorEntity):
    def __init__(
        self,
        coordinator: XeniaDataUpdateCoordinator,
        entity_description: XeniaSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description: XeniaSensorEntityDescription = entity_description
        self._attr_unique_id = (
            f"{coordinator.config_entry.data[CONF_HOST]}_{entity_description.key}"
        )

    @property
    def native_value(self) -> StateType:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def entity_category(self) -> EntityCategory | None:
        if self.entity_description.entity_category_fn is not None:
            return self.entity_description.entity_category_fn(self.coordinator.data)
        return super().entity_category
