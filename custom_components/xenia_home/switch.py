"""Switch platform for the Xenia espresso machine."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import XENIA_DOMAIN, PowerOnBehavior
from .coordinator import XeniaConfigEntry, XeniaDataUpdateCoordinator
from .entity import XeniaEntity
from .errors import machine_write
from .xenia import MachineStatus, SteamBoilerStatus

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: XeniaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the power, eco and steam-boiler switches."""
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
    """Main on/off switch (honours the configured power-on behaviour)."""

    def __init__(self, coordinator: XeniaDataUpdateCoordinator) -> None:
        """Initialize the power switch."""
        super().__init__(coordinator)
        self._attr_translation_key = "power"
        self._attr_unique_id = (
            f"{XENIA_DOMAIN}_power_{coordinator.config_entry.data[CONF_HOST]}"
        )

    @property
    def is_on(self):
        """Return True if the machine is in any heating-or-active state."""
        ma_status = self.coordinator.data.overview.ma_status
        return ma_status in [
            MachineStatus.ON,
            MachineStatus.BREWING,
            MachineStatus.DRAINING,
        ]

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the machine on, respecting the configured power-on behaviour."""
        sb_on = self.runtime_data.power_on_behavior == PowerOnBehavior.STEAM_ON
        async with machine_write():
            await self.coordinator.xenia.machine_turn_on(sb_on=sb_on)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the machine off."""
        async with machine_write():
            await self.coordinator.xenia.machine_turn_off()
        await self.coordinator.async_request_refresh()


class XeniaEcoSwitch(XeniaEntity, SwitchEntity):
    """Eco-mode switch."""

    def __init__(self, coordinator: XeniaDataUpdateCoordinator) -> None:
        """Initialize the eco switch."""
        super().__init__(coordinator)
        self._attr_translation_key = "eco_mode"
        self._attr_unique_id = (
            f"{XENIA_DOMAIN}_eco_mode_{coordinator.config_entry.data[CONF_HOST]}"
        )

    @property
    def available(self) -> bool:
        """Available only when the machine is on (in any heating state)."""
        return self.coordinator.data.overview.ma_status in [
            MachineStatus.ON,
            MachineStatus.BREWING,
            MachineStatus.DRAINING,
            MachineStatus.ECO,
        ]

    @property
    def is_on(self):
        """Return True when the machine is currently in eco mode."""
        return self.coordinator.data.overview.ma_status == MachineStatus.ECO

    async def async_turn_on(self, **kwargs) -> None:
        """Switch the machine into eco mode."""
        async with machine_write():
            await self.coordinator.xenia.machine_set_eco()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        """Leave eco mode by re-applying the configured power-on behaviour."""
        sb_on = self.runtime_data.power_on_behavior == PowerOnBehavior.STEAM_ON
        async with machine_write():
            await self.coordinator.xenia.machine_turn_on(sb_on=sb_on)
        await self.coordinator.async_request_refresh()


class XeniaSteamBoilerSwitch(XeniaEntity, SwitchEntity):
    """Steam-boiler on/off switch."""

    def __init__(self, coordinator: XeniaDataUpdateCoordinator) -> None:
        """Initialize the steam-boiler switch."""
        super().__init__(coordinator)
        self._attr_translation_key = "steam_boiler_power"
        self._attr_unique_id = (
            f"{XENIA_DOMAIN}_steam_boiler_power_"
            f"{coordinator.config_entry.data[CONF_HOST]}"
        )

    @property
    def available(self) -> bool:
        """Available only when the machine is on."""
        return self.coordinator.data.overview.ma_status in [
            MachineStatus.ON,
            MachineStatus.BREWING,
            MachineStatus.DRAINING,
        ]

    @property
    def is_on(self):
        """Return True when the steam boiler is on."""
        return self.coordinator.data.overview.sb_status == SteamBoilerStatus.ON

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the steam boiler on."""
        async with machine_write():
            await self.coordinator.xenia.sb_turn_on()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the steam boiler off."""
        async with machine_write():
            await self.coordinator.xenia.sb_turn_off()
        await self.coordinator.async_request_refresh()
