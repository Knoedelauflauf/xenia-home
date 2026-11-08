"""Binary sensor platform for the Xenia espresso machine."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import XeniaConfigEntry, XeniaDataUpdateCoordinator
from .entity import XeniaEntity

PARALLEL_UPDATES = 0

WATER_TANK_EMPTY = 2


async def async_setup_entry(
    hass: HomeAssistant,
    entry: XeniaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the water tank sensor."""
    async_add_entities([XeniaWaterTankSensor(entry.runtime_data.coordinator)])


class XeniaWaterTankSensor(XeniaEntity, BinarySensorEntity):
    """On when the water tank is empty."""

    _attr_translation_key = "water_tank_empty"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: XeniaDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{self.machine_id}_water_tank_empty"

    @property
    def is_on(self) -> bool:
        """Return whether the water tank is empty."""
        return (
            self.coordinator.data.overview_single.pu_sens_water_tank_level
            == WATER_TANK_EMPTY
        )
