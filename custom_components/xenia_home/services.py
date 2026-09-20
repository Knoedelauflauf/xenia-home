"""The execute_script action."""

from homeassistant.const import ATTR_CONFIG_ENTRY_ID
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import service
from homeassistant.helpers.selector import ConfigEntrySelector
import voluptuous as vol

from .const import XENIA_DOMAIN
from .coordinator import XeniaConfigEntry
from .errors import machine_write

SERVICE_EXECUTE_SCRIPT = "execute_script"
ATTR_SCRIPT_ID = "script_id"
ATTR_SCRIPT_NAME = "script_name"

SERVICE_EXECUTE_SCRIPT_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): ConfigEntrySelector(
            {"integration": XENIA_DOMAIN}
        ),
        vol.Optional(ATTR_SCRIPT_ID): vol.Coerce(int),
        vol.Optional(ATTR_SCRIPT_NAME): str,
    }
)


def _get_entry(hass: HomeAssistant, call: ServiceCall) -> XeniaConfigEntry:
    """Return the addressed config entry, or the only loaded one."""
    if (entry_id := call.data.get(ATTR_CONFIG_ENTRY_ID)) is not None:
        return service.async_get_config_entry(hass, XENIA_DOMAIN, entry_id)
    # Drop this fallback once the minimum HA is 2026.7; async_get_config_entry
    # then accepts a missing entry_id.
    entries = hass.config_entries.async_loaded_entries(XENIA_DOMAIN)
    if not entries:
        raise ServiceValidationError(
            translation_domain=XENIA_DOMAIN, translation_key="entry_not_loaded"
        )
    if len(entries) > 1:
        raise ServiceValidationError(
            translation_domain=XENIA_DOMAIN, translation_key="multiple_entries"
        )
    return entries[0]


async def _execute_script(call: ServiceCall) -> None:
    runtime = _get_entry(call.hass, call).runtime_data
    script_id = call.data.get(ATTR_SCRIPT_ID)
    script_name = call.data.get(ATTR_SCRIPT_NAME)
    if script_id is None and script_name is None:
        raise ServiceValidationError(
            translation_domain=XENIA_DOMAIN, translation_key="script_required"
        )
    if script_id is None:
        scripts = runtime.config_coordinator.data.scripts
        script_id = next(
            (sid for sid, title in scripts.items() if title == script_name), None
        )
        if script_id is None:
            raise ServiceValidationError(
                translation_domain=XENIA_DOMAIN,
                translation_key="script_not_found",
                translation_placeholders={"script_name": str(script_name)},
            )
    async with machine_write():
        await runtime.coordinator.xenia.execute_script(script_id)


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration's actions."""
    hass.services.async_register(
        XENIA_DOMAIN,
        SERVICE_EXECUTE_SCRIPT,
        _execute_script,
        schema=SERVICE_EXECUTE_SCRIPT_SCHEMA,
    )
