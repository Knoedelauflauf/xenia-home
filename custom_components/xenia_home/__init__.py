"""Xenia Espresso Machine integration."""

import logging

import voluptuous as vol

from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import PLATFORMS, XENIA_DOMAIN
from .coordinator import (
    XeniaConfigCoordinator,
    XeniaConfigEntry,
    XeniaDataUpdateCoordinator,
    XeniaRuntimeData,
)
from .xenia import Xenia

_LOGGER = logging.getLogger(__name__)

SERVICE_EXECUTE_SCRIPT = "execute_script"
ATTR_SCRIPT_ID = "script_id"
ATTR_SCRIPT_NAME = "script_name"

SERVICE_EXECUTE_SCRIPT_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_SCRIPT_ID): vol.Coerce(int),
        vol.Optional(ATTR_SCRIPT_NAME): str,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: XeniaConfigEntry) -> bool:
    """Set up Xenia from a config entry."""
    host = entry.data[CONF_HOST]
    session = async_get_clientsession(hass)
    xenia = Xenia(host, session)

    coordinator = XeniaDataUpdateCoordinator(hass, entry, xenia)
    config_coordinator = XeniaConfigCoordinator(hass, entry, xenia)

    await config_coordinator.async_config_entry_first_refresh()
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = XeniaRuntimeData(
        coordinator=coordinator,
        config_coordinator=config_coordinator,
    )

    async def handle_execute_script(call: ServiceCall) -> None:
        """Handle the execute_script service call."""
        script_id = call.data.get(ATTR_SCRIPT_ID)
        script_name = call.data.get(ATTR_SCRIPT_NAME)

        if script_id is None and script_name is None:
            raise ServiceValidationError("Either script_id or script_name is required")

        if script_id is None:
            # Look up script ID by name
            scripts = config_coordinator.data.scripts
            for sid, title in scripts.items():
                if title == script_name:
                    script_id = sid
                    break
            if script_id is None:
                raise ServiceValidationError(f"Script '{script_name}' not found")

        await xenia.execute_script(script_id)

    hass.services.async_register(
        XENIA_DOMAIN,
        SERVICE_EXECUTE_SCRIPT,
        handle_execute_script,
        schema=SERVICE_EXECUTE_SCRIPT_SCHEMA,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: XeniaConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    # Only remove the service when no more entries remain loaded
    if unload_ok and not hass.config_entries.async_entries(XENIA_DOMAIN):
        hass.services.async_remove(XENIA_DOMAIN, SERVICE_EXECUTE_SCRIPT)
    return unload_ok
