from homeassistant.components.switch import SwitchEntity
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_POWER_ON_BEHAVIOR,
    DEFAULT_POWER_ON_BEHAVIOR,
    XENIA_DOMAIN,
    PowerOnBehavior,
)
from .coordinator import XeniaConfigEntry, XeniaDataUpdateCoordinator
from .entity import XeniaEntity
from .xenia import MachineStatus, SteamBoilerStatus

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: XeniaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            XeniaPowerSwitch(coordinator),
            XeniaEcoSwitch(coordinator),
            XeniaSteamBoilerSwitch(coordinator),
        ],
        True,
    )


class XeniaPowerSwitch(XeniaEntity, SwitchEntity):
    def __init__(self, coordinator: XeniaDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_translation_key = "power"
        self._attr_unique_id = (
            f"{XENIA_DOMAIN}_power_{coordinator.config_entry.data[CONF_HOST]}"
        )
        self._attr_icon = "mdi:coffee-maker"

    @property
    def is_on(self):
        ma_status = self.coordinator.data.overview.ma_status
        return ma_status in [
            MachineStatus.ON,
            MachineStatus.BREWING,
            MachineStatus.DRAINING,
        ]

    async def async_turn_on(self, **kwargs) -> None:
        behavior = self.coordinator.config_entry.options.get(
            CONF_POWER_ON_BEHAVIOR, DEFAULT_POWER_ON_BEHAVIOR
        )
        if behavior == PowerOnBehavior.STEAM_ON:
            await self.coordinator.xenia.machine_turn_on()
        elif behavior == PowerOnBehavior.STEAM_OFF:
            await self.coordinator.xenia.machine_turn_on(False)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.xenia.machine_turn_off()
        await self.coordinator.async_request_refresh()


class XeniaEcoSwitch(XeniaEntity, SwitchEntity):
    def __init__(self, coordinator: XeniaDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_translation_key = "eco_mode"
        self._attr_unique_id = (
            f"{XENIA_DOMAIN}_eco_mode_{coordinator.config_entry.data[CONF_HOST]}"
        )
        self._attr_icon = "mdi:sprout"

    @property
    def available(self) -> bool:
        return self.coordinator.data.overview.ma_status in [
            MachineStatus.ON,
            MachineStatus.BREWING,
            MachineStatus.DRAINING,
            MachineStatus.ECO,
        ]

    @property
    def is_on(self):
        return self.coordinator.data.overview.ma_status == MachineStatus.ECO

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.xenia.machine_set_eco()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        behavior = self.coordinator.config_entry.options.get(
            CONF_POWER_ON_BEHAVIOR, DEFAULT_POWER_ON_BEHAVIOR
        )
        if behavior == PowerOnBehavior.STEAM_ON:
            await self.coordinator.xenia.machine_turn_on()
        elif behavior == PowerOnBehavior.STEAM_OFF:
            await self.coordinator.xenia.machine_turn_on(False)
        await self.coordinator.async_request_refresh()


class XeniaSteamBoilerSwitch(XeniaEntity, SwitchEntity):
    def __init__(self, coordinator: XeniaDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_translation_key = "steam_boiler_power"
        self._attr_unique_id = (
            f"{XENIA_DOMAIN}_steam_boiler_power_"
            f"{coordinator.config_entry.data[CONF_HOST]}"
        )
        self._attr_icon = "mdi:kettle-steam"

    @property
    def available(self) -> bool:
        return self.coordinator.data.overview.ma_status in [
            MachineStatus.ON,
            MachineStatus.BREWING,
            MachineStatus.DRAINING,
        ]

    @property
    def is_on(self):
        return self.coordinator.data.overview.sb_status == SteamBoilerStatus.ON

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.xenia.sb_turn_on()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.xenia.sb_turn_off()
        await self.coordinator.async_request_refresh()
