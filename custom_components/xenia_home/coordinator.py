"""Data update coordinators for the Xenia espresso machine."""

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_MANAGED_SCRIPT_ID,
    CONF_WEIGHT_MANAGEMENT_ENABLED,
    POLL_INTERVAL_ACTIVE,
    POLL_INTERVAL_CONFIG,
    POLL_INTERVAL_CONFIG_RETRY,
    POLL_INTERVAL_IDLE,
    PowerOnBehavior,
)
from .errors import REQUEST_ERRORS, update_failed
from .shot_store import XeniaShotStore
from .xenia import (
    ACTIVE_STATUSES,
    MachineStatus,
    Xenia,
    XeniaMachineData,
    XeniaOverviewData,
    XeniaOverviewSingleData,
)

_LOGGER = logging.getLogger(__name__)


# Built-in scripts the script list leaves out.
BUILTIN_SCRIPTS: dict[int, str] = {
    0: "None",
    1: "Espresso",
    2: "Espresso endless",
}


@dataclass
class XeniaCoordinatorData:
    """Live data of the machine."""

    overview: XeniaOverviewData
    overview_single: XeniaOverviewSingleData
    shot_start_time: datetime | None = None


@dataclass
class XeniaConfigData:
    """Slowly changing data of the machine."""

    machine: XeniaMachineData
    # Script titles, with the id added to titles several scripts share.
    scripts: dict[int, str] = field(default_factory=dict)
    switches: dict[str, int] = field(default_factory=dict)
    managed_script_instruction: str | None = None
    managed_script_name: str | None = None


@dataclass
class XeniaRuntimeData:
    """Runtime data for the integration."""

    coordinator: XeniaDataUpdateCoordinator
    config_coordinator: XeniaConfigCoordinator
    shot_store: XeniaShotStore
    power_on_behavior: PowerOnBehavior = PowerOnBehavior.STEAM_OFF
    selected_script_id: int | None = None


type XeniaConfigEntry = ConfigEntry[XeniaRuntimeData]


class XeniaDataUpdateCoordinator(DataUpdateCoordinator[XeniaCoordinatorData]):
    """Poll the live data, faster while the machine is on."""

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
            update_interval=POLL_INTERVAL_IDLE,
            config_entry=config_entry,
        )
        self.xenia = xenia

    async def _async_update_data(self) -> XeniaCoordinatorData:
        """Fetch data and adjust the polling interval based on machine state."""
        try:
            overview = await self.xenia.get_overview()
            overview_single = await self.xenia.get_overview_single()
        except REQUEST_ERRORS as err:
            raise update_failed(err) from err

        self.update_interval = (
            POLL_INTERVAL_ACTIVE
            if overview.ma_status in ACTIVE_STATUSES
            else POLL_INTERVAL_IDLE
        )

        shot_start_time = None
        if overview.ma_status == MachineStatus.BREWING:
            previous = self.data.shot_start_time if self.data is not None else None
            shot_start_time = previous or dt_util.utcnow()

        return XeniaCoordinatorData(overview, overview_single, shot_start_time)


class XeniaConfigCoordinator(DataUpdateCoordinator[XeniaConfigData]):
    """Poll the machine info, scripts, switches and managed script hourly."""

    config_entry: XeniaConfigEntry

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
            update_interval=POLL_INTERVAL_CONFIG,
            config_entry=config_entry,
        )
        self.xenia = xenia

    async def _async_update_data(self) -> XeniaConfigData:
        """Fetch config data: machine info, scripts, switches, and managed script."""
        try:
            machine = await self.xenia.get_machine()
            user_scripts = await self.xenia.get_scripts()
            switches = await self.xenia.get_switches()
        except REQUEST_ERRORS as err:
            self.update_interval = POLL_INTERVAL_CONFIG_RETRY
            raise update_failed(err) from err
        self.update_interval = POLL_INTERVAL_CONFIG
        titles = {**BUILTIN_SCRIPTS, **user_scripts}
        counts = Counter(titles.values())
        scripts = {
            script_id: title if counts[title] == 1 else f"{title} ({script_id})"
            for script_id, title in titles.items()
        }

        managed_instruction: str | None = None
        managed_name: str | None = None
        options = self.config_entry.options
        if options.get(CONF_WEIGHT_MANAGEMENT_ENABLED):
            script_id = options.get(CONF_MANAGED_SCRIPT_ID)
            if script_id is not None:
                try:
                    script_data = await self.xenia.read_script(int(script_id))
                except REQUEST_ERRORS as err:
                    _LOGGER.warning(
                        "Failed to read managed script %s: %s", script_id, err
                    )
                    self.update_interval = POLL_INTERVAL_CONFIG_RETRY
                else:
                    content = script_data.get("Content") or None
                    title = script_data.get("Title") or None
                    if content is None:
                        _LOGGER.warning(
                            "Managed script %s no longer exists on the machine; "
                            "reconfigure weight management to pick another script",
                            script_id,
                        )
                    managed_instruction = content
                    managed_name = title

        return XeniaConfigData(
            machine=machine,
            scripts=scripts,
            switches=switches,
            managed_script_instruction=managed_instruction,
            managed_script_name=managed_name,
        )
