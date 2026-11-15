"""Switch platform for the Xenia espresso machine."""

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import PowerOnBehavior
from .coordinator import XeniaConfigEntry, XeniaDataUpdateCoordinator
from .entity import XeniaEntity
from .errors import machine_write
from .xenia import ACTIVE_STATUSES, MachineStatus, SteamBoilerStatus

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: XeniaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the power, eco and steam boiler switches."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            XeniaPowerSwitch(coordinator),
            XeniaEcoSwitch(coordinator),
            XeniaSteamBoilerSwitch(coordinator),
        ]
    )


class XeniaSwitch(XeniaEntity, SwitchEntity):
    """Switch that polls the machine after every write."""

    def __init__(self, coordinator: XeniaDataUpdateCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{self.machine_id}_{self.entity_description.key}"

    async def _async_turn_machine_on(self) -> None:
        steam_on = self.runtime_data.power_on_behavior is PowerOnBehavior.STEAM_ON
        async with machine_write():
            await self.coordinator.xenia.machine_turn_on(sb_on=steam_on)
        await self.coordinator.async_request_refresh()


class XeniaPowerSwitch(XeniaSwitch):
    """Turn the machine on, honouring the power on behavior, or off."""

    entity_description = SwitchEntityDescription(key="power", translation_key="power")

    @property
    def is_on(self) -> bool:
        """Return whether the machine is on."""
        return self.coordinator.data.overview.ma_status in ACTIVE_STATUSES

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the machine on."""
        await self._async_turn_machine_on()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the machine off."""
        async with machine_write():
            await self.coordinator.xenia.machine_turn_off()
        await self.coordinator.async_request_refresh()


class XeniaEcoSwitch(XeniaSwitch):
    """Put the running machine into eco mode or back."""

    entity_description = SwitchEntityDescription(
        key="eco_mode", translation_key="eco_mode"
    )

    @property
    def available(self) -> bool:
        """Return whether the machine is on or in eco mode."""
        status = self.coordinator.data.overview.ma_status
        return super().available and (
            status in ACTIVE_STATUSES or status is MachineStatus.ECO
        )

    @property
    def is_on(self) -> bool:
        """Return whether the machine is in eco mode."""
        return self.coordinator.data.overview.ma_status is MachineStatus.ECO

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enter eco mode."""
        async with machine_write():
            await self.coordinator.xenia.machine_set_eco()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Leave eco mode by turning the machine on."""
        await self._async_turn_machine_on()


class XeniaSteamBoilerSwitch(XeniaSwitch):
    """Turn the steam boiler of the running machine on or off."""

    entity_description = SwitchEntityDescription(
        key="steam_boiler_power", translation_key="steam_boiler_power"
    )

    @property
    def available(self) -> bool:
        """Return whether the machine is on."""
        return (
            super().available
            and self.coordinator.data.overview.ma_status in ACTIVE_STATUSES
        )

    @property
    def is_on(self) -> bool:
        """Return whether the steam boiler is on."""
        return self.coordinator.data.overview.sb_status is SteamBoilerStatus.ON

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the steam boiler on."""
        async with machine_write():
            await self.coordinator.xenia.sb_turn_on()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the steam boiler off."""
        async with machine_write():
            await self.coordinator.xenia.sb_turn_off()
        await self.coordinator.async_request_refresh()
