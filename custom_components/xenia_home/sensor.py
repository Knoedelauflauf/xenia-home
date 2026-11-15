"""Sensor platform for the Xenia espresso machine."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Final, override

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfEnergy,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import (
    XeniaConfigEntry,
    XeniaCoordinatorData,
    XeniaDataUpdateCoordinator,
)
from .entity import XeniaEntity
from .xenia import MachineStatus

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class XeniaSensorEntityDescription(SensorEntityDescription):
    """Describes a sensor of the live data."""

    value_fn: Callable[[XeniaCoordinatorData], StateType | datetime]
    exists_fn: Callable[[XeniaCoordinatorData], bool] = lambda data: True


SENSOR_TYPES: Final[tuple[XeniaSensorEntityDescription, ...]] = (
    XeniaSensorEntityDescription(
        key="brew_group_temperature",
        translation_key="brew_group_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.overview.bg_sens_temp_a,
    ),
    XeniaSensorEntityDescription(
        key="brew_boiler_temperature",
        translation_key="brew_boiler_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.overview.bb_sens_temp_a,
    ),
    XeniaSensorEntityDescription(
        key="pump_pressure",
        translation_key="pump_pressure",
        native_unit_of_measurement=UnitOfPressure.BAR,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.overview.pu_sens_press,
    ),
    XeniaSensorEntityDescription(
        key="steam_boiler_pressure",
        translation_key="steam_boiler_pressure",
        native_unit_of_measurement=UnitOfPressure.BAR,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.overview.sb_sens_press,
    ),
    XeniaSensorEntityDescription(
        key="electric_current",
        translation_key="electric_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.overview.ma_cur_pwr,
    ),
    XeniaSensorEntityDescription(
        key="total_energy",
        translation_key="total_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.overview.ma_energy_total_kwh,
    ),
    XeniaSensorEntityDescription(
        key="extractions",
        translation_key="extractions",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.overview.ma_extractions,
    ),
    XeniaSensorEntityDescription(
        key="operating_hours",
        translation_key="operating_hours",
        native_unit_of_measurement=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: (
            None
            if (minutes := data.overview.ma_operating_hours) is None
            else minutes / 60
        ),
    ),
    XeniaSensorEntityDescription(
        key="scale_flow_rate",
        translation_key="scale_flow_rate",
        native_unit_of_measurement="g/s",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.overview.pu_sens_scale_rate,
        exists_fn=lambda data: data.overview.pu_sens_scale_rate is not None,
    ),
    XeniaSensorEntityDescription(
        key="status",
        translation_key="status",
        device_class=SensorDeviceClass.ENUM,
        options=[
            status.name.lower()
            for status in MachineStatus
            if status is not MachineStatus.UNKNOWN
        ],
        value_fn=lambda data: (
            None
            if data.overview.ma_status is MachineStatus.UNKNOWN
            else data.overview.ma_status.name.lower()
        ),
    ),
    XeniaSensorEntityDescription(
        key="shot_start_time",
        translation_key="shot_start_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.shot_start_time,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: XeniaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors the machine supports."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        XeniaSensor(coordinator, description)
        for description in SENSOR_TYPES
        if description.exists_fn(coordinator.data)
    )


class XeniaSensor(XeniaEntity, SensorEntity):
    """Sensor of the live data."""

    entity_description: XeniaSensorEntityDescription

    def __init__(
        self,
        coordinator: XeniaDataUpdateCoordinator,
        entity_description: XeniaSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        self._attr_unique_id = f"{self.machine_id}_{entity_description.key}"

    @property
    @override
    def native_value(self) -> StateType | datetime:
        """Return the sensor value, or None for zeroed cumulative counters."""
        value = self.entity_description.value_fn(self.coordinator.data)
        if (
            self.entity_description.state_class == SensorStateClass.TOTAL_INCREASING
            and not value
        ):
            return None
        return value
