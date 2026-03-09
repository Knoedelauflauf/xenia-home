from dataclasses import dataclass, field
from datetime import timedelta
import logging

from aiohttp import ClientError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_MANAGED_SCRIPT_ID, CONF_WEIGHT_MANAGEMENT_ENABLED
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
    managed_script_instruction: str | None = None
    managed_script_name: str | None = None


@dataclass
class XeniaRuntimeData:
    """Runtime data for the integration."""

    coordinator: "XeniaDataUpdateCoordinator"
    config_coordinator: "XeniaConfigCoordinator"


type XeniaConfigEntry = ConfigEntry[XeniaRuntimeData]


class XeniaDataUpdateCoordinator(DataUpdateCoordinator[XeniaCoordinatorData]):
    """Xenia device data update coordinator for fast polling."""

    config_entry: XeniaConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: XeniaConfigEntry,
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
            overview_single = await self.xenia.get_overview_single()
        except (ClientError, OSError, TimeoutError) as err:
            raise UpdateFailed(f"Xenia fetch failed: {err}") from err
        return XeniaCoordinatorData(overview, overview_single)


class XeniaConfigCoordinator(DataUpdateCoordinator[XeniaConfigData]):
    """Xenia coordinator for config/slow data (scripts, switches, machine info)."""

    config_entry: XeniaConfigEntry
    selected_script_id: int | None = None

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: XeniaConfigEntry,
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
        self.config_entry = config_entry
        self.xenia = xenia

    async def _async_update_data(self) -> XeniaConfigData:
        try:
            machine = await self.xenia.get_machine()
            user_scripts = await self.xenia.get_scripts()
            switches = await self.xenia.get_switches()
        except (ClientError, OSError, TimeoutError) as err:
            raise UpdateFailed(f"Xenia config fetch failed: {err}") from err
        scripts = {**BUILTIN_SCRIPTS, **user_scripts}

        managed_instruction: str | None = None
        managed_name: str | None = None
        options = self.config_entry.options
        if options.get(CONF_WEIGHT_MANAGEMENT_ENABLED):
            script_id = options.get(CONF_MANAGED_SCRIPT_ID)
            if script_id is not None:
                try:
                    script_data = await self.xenia.read_script(int(script_id))
                    managed_instruction = script_data.get("Content")
                    managed_name = script_data.get("Title")
                except (ClientError, OSError, TimeoutError) as err:
                    _LOGGER.warning("Failed to read managed script %s: %s", script_id, err)

        return XeniaConfigData(
            machine=machine,
            scripts=scripts,
            switches=switches,
            managed_script_instruction=managed_instruction,
            managed_script_name=managed_name,
        )
