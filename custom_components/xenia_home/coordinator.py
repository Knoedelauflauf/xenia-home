"""Data update coordinators for the Xenia espresso machine."""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
import logging
from typing import override

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    COMMAND_REFRESH_DELAY,
    CONF_MANAGED_SCRIPT_ID,
    CONF_WEIGHT_MANAGEMENT_ENABLED,
    POLL_INTERVAL_ACTIVE,
    POLL_INTERVAL_CONFIG,
    POLL_INTERVAL_CONFIG_RETRY,
    POLL_INTERVAL_IDLE,
    XENIA_DOMAIN,
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
    shot_start_time: datetime | None


@dataclass
class XeniaConfigData:
    """Slowly changing data of the machine."""

    machine: XeniaMachineData
    # Script titles, with the id added to titles several scripts share.
    scripts: dict[int, str]
    switches: dict[str, int]
    managed_script_instruction: str | None


@dataclass
class XeniaRuntimeData:
    """Runtime data for the integration."""

    coordinator: XeniaDataUpdateCoordinator
    config_coordinator: XeniaConfigCoordinator
    shot_store: XeniaShotStore
    power_on_behavior: PowerOnBehavior = PowerOnBehavior.STEAM_OFF
    selected_script_id: int | None = None


type XeniaConfigEntry = ConfigEntry[XeniaRuntimeData]


class XeniaCoordinator[DataT](DataUpdateCoordinator[DataT]):
    """Coordinator that polls again once the machine shows a command's effect."""

    _unsub_command_refresh: CALLBACK_TYPE | None = None

    @callback
    def async_refresh_after_command(self) -> None:
        """Poll the machine shortly after a command; it reports the new state late."""
        self._cancel_command_refresh()
        self._unsub_command_refresh = async_call_later(
            self.hass, COMMAND_REFRESH_DELAY, self._async_command_refresh
        )

    async def _async_command_refresh(self, _now: datetime) -> None:
        self._unsub_command_refresh = None
        await self.async_refresh()

    def _cancel_command_refresh(self) -> None:
        if self._unsub_command_refresh is not None:
            self._unsub_command_refresh()
            self._unsub_command_refresh = None

    @override
    async def async_shutdown(self) -> None:
        """Cancel a pending poll after a command, then shut down."""
        self._cancel_command_refresh()
        await super().async_shutdown()


class XeniaDataUpdateCoordinator(XeniaCoordinator[XeniaCoordinatorData]):
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

    @override
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


class XeniaConfigCoordinator(XeniaCoordinator[XeniaConfigData]):
    """Poll the machine info, scripts, switches and managed script hourly."""

    config_entry: XeniaConfigEntry
    _managed_script_unreadable = False

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

    @override
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
        options = self.config_entry.options
        issue_id = f"managed_script_missing_{self.config_entry.entry_id}"
        if options.get(CONF_WEIGHT_MANAGEMENT_ENABLED):
            script_id = options[CONF_MANAGED_SCRIPT_ID]
            try:
                script = await self.xenia.read_script(script_id)
            except REQUEST_ERRORS as err:
                if not self._managed_script_unreadable:
                    _LOGGER.info("Failed to read managed script %s: %s", script_id, err)
                    self._managed_script_unreadable = True
                self.update_interval = POLL_INTERVAL_CONFIG_RETRY
            else:
                if self._managed_script_unreadable:
                    _LOGGER.info("Managed script %s can be read again", script_id)
                    self._managed_script_unreadable = False
                managed_instruction = script.get("Content") or None
                if managed_instruction is None:
                    ir.async_create_issue(
                        self.hass,
                        XENIA_DOMAIN,
                        issue_id,
                        is_fixable=False,
                        severity=ir.IssueSeverity.WARNING,
                        translation_key="managed_script_missing",
                        translation_placeholders={
                            "script_id": str(script_id),
                            "title": self.config_entry.title,
                        },
                    )
                else:
                    ir.async_delete_issue(self.hass, XENIA_DOMAIN, issue_id)
        else:
            ir.async_delete_issue(self.hass, XENIA_DOMAIN, issue_id)

        return XeniaConfigData(
            machine=machine,
            scripts=scripts,
            switches=switches,
            managed_script_instruction=managed_instruction,
        )
