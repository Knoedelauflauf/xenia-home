import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
import logging

from aiohttp import ClientSession

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .xenia import Xenia, XeniaMachineData, XeniaOverviewData, XeniaOverviewSingleData

_LOGGER = logging.getLogger(__name__)


# Built-in scripts that are not returned by the API
BUILTIN_SCRIPTS: dict[int, str] = {
    0: "None",
    1: "Espresso",
    2: "Espresso endless",
}


@dataclass
class XeniaCoordinatorData:
    """Data type for fast polling coordinator."""

    overview: XeniaOverviewData
    overview_single: XeniaOverviewSingleData


@dataclass
class XeniaConfigData:
    """Data type for config/slow data coordinator."""

    machine: XeniaMachineData
    scripts: dict[int, str] = field(default_factory=dict)
    switches: dict[str, int] = field(default_factory=dict)


@dataclass
class XeniaRuntimeData:
    """Runtime data for the integration."""

    coordinator: "XeniaDataUpdateCoordinator"
    config_coordinator: "XeniaConfigCoordinator"


type XeniaConfigEntry = ConfigEntry[XeniaRuntimeData]


class XeniaDataUpdateCoordinator(DataUpdateCoordinator[XeniaCoordinatorData]):
    """Xenia device data update coordinator for fast polling."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        xenia: Xenia,
    ) -> None:
        """Initialize the Xenia device coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{config_entry.entry_id}_data",
            update_interval=timedelta(seconds=1),
            config_entry=config_entry,
        )
        self.xenia = xenia

    async def _async_update_data(self) -> XeniaCoordinatorData:
        try:
            overview = await self.xenia.get_overview()
            await asyncio.sleep(0.5)
            overview_single = await self.xenia.get_overview_single()
            return XeniaCoordinatorData(overview, overview_single)
        except Exception as err:
            raise UpdateFailed(f"Xenia fetch failed: {err}") from err


class XeniaConfigCoordinator(DataUpdateCoordinator[XeniaConfigData]):
    """Xenia coordinator for config/slow data (scripts, switches, machine info)."""

    selected_script_id: int | None = None

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        xenia: Xenia,
    ) -> None:
        """Initialize the Xenia config coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{config_entry.entry_id}_config",
            update_interval=timedelta(hours=1),
            config_entry=config_entry,
        )
        self.xenia = xenia

    async def _async_update_data(self) -> XeniaConfigData:
        try:
            machine = await self.xenia.get_machine()
            user_scripts = await self.xenia.get_scripts()
            scripts = {**BUILTIN_SCRIPTS, **user_scripts}
            switches = await self.xenia.get_switches()
            return XeniaConfigData(
                machine=machine,
                scripts=scripts,
                switches=switches,
            )
        except Exception as err:
            raise UpdateFailed(f"Xenia config fetch failed: {err}") from err
