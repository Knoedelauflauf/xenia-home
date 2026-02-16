from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import XeniaConfigEntry, XeniaDataUpdateCoordinator
from .entity import XeniaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: XeniaConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    coordinator = entry.runtime_data.coordinator
    async_add_entities([XeniaWaterTankSensor(coordinator)])


class XeniaWaterTankSensor(XeniaEntity, BinarySensorEntity):
    def __init__(self, coordinator: XeniaDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_translation_key = "water_tank_empty"
        self._attr_unique_id = (
            f"{coordinator.config_entry.data[CONF_HOST]}_water_tank_empty"
        )
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM
        self._attr_icon = "mdi:water-off"

    @property
    def is_on(self) -> bool:
        # is_on = True means "problem" (tank empty)
        # Xenia returns 2 when empty, 1 when water present
        return self.coordinator.data.overview_single.pu_sens_water_tank_level == 2
