"""Binary sensor platform for Xenia espresso machine."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import XeniaConfigEntry, XeniaDataUpdateCoordinator
from .entity import XeniaEntity, machine_id

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: XeniaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the water-tank binary sensor."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities([XeniaWaterTankSensor(coordinator)])


class XeniaWaterTankSensor(XeniaEntity, BinarySensorEntity):
    """Reports whether the water tank is empty."""

    def __init__(self, coordinator: XeniaDataUpdateCoordinator) -> None:
        """Initialize the water-tank sensor."""
        super().__init__(coordinator)
        self._attr_translation_key = "water_tank_empty"
        self._attr_unique_id = (
            f"{machine_id(coordinator.config_entry)}_water_tank_empty"
        )
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM

    @property
    def is_on(self) -> bool:
        """Return True when the water tank is empty (problem state)."""
        # Xenia returns 2 when empty, 1 when water present
        return self.coordinator.data.overview_single.pu_sens_water_tank_level == 2
