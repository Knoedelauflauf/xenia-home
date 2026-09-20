"""Xenia Espresso Machine integration."""

import logging

from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_POWER_ON_BEHAVIOR,
    PLATFORMS,
    POWER_ON_BEHAVIOR_OPTIONS,
    REMOVED_OPTION_KEYS,
    XENIA_DOMAIN,
    PowerOnBehavior,
)
from .coordinator import (
    XeniaConfigCoordinator,
    XeniaConfigEntry,
    XeniaDataUpdateCoordinator,
    XeniaRuntimeData,
)
from .recorder_import import async_import_recorder_shots
from .services import async_setup_services
from .shot_store import XeniaShotStore
from .websocket import async_register_commands
from .xenia import Xenia

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(XENIA_DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration's actions and websocket commands."""
    async_register_commands(hass)
    async_setup_services(hass)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: XeniaConfigEntry) -> None:
    """Reload on an options or host change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: XeniaConfigEntry) -> bool:
    """Set up Xenia from a config entry."""
    host = entry.data[CONF_HOST]
    session = async_get_clientsession(hass)
    xenia = Xenia(host, session)

    coordinator = XeniaDataUpdateCoordinator(hass, entry, xenia)
    config_coordinator = XeniaConfigCoordinator(hass, entry, xenia)

    await config_coordinator.async_config_entry_first_refresh()
    await coordinator.async_config_entry_first_refresh()

    shot_store = XeniaShotStore(hass, entry.entry_id)
    await shot_store.async_load()

    entry.runtime_data = XeniaRuntimeData(
        coordinator=coordinator,
        config_coordinator=config_coordinator,
        shot_store=shot_store,
    )
    # Strip before the update listener is added, or this reloads the entry.
    options = {k: v for k, v in entry.options.items() if k not in REMOVED_OPTION_KEYS}
    if (
        value := options.pop(CONF_POWER_ON_BEHAVIOR, None)
    ) in POWER_ON_BEHAVIOR_OPTIONS:
        entry.runtime_data.power_on_behavior = PowerOnBehavior(value)
    if options != entry.options:
        hass.config_entries.async_update_entry(entry, options=options)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if not shot_store.migrated:
        entry.async_create_background_task(
            hass,
            async_import_recorder_shots(hass, entry, shot_store),
            "xenia_home_recorder_import",
        )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: XeniaConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: XeniaConfigEntry) -> None:
    """Delete the entry's shot history files."""
    store = XeniaShotStore(hass, entry.entry_id)
    await store.async_load()
    await store.async_remove()
