"""The execute_script action."""

from homeassistant.const import ATTR_CONFIG_ENTRY_ID
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import service
from homeassistant.helpers.selector import ConfigEntrySelector
import probatio

from .const import XENIA_DOMAIN
from .coordinator import XeniaConfigEntry
from .errors import async_write

SERVICE_EXECUTE_SCRIPT = "execute_script"
ATTR_SCRIPT_ID = "script_id"
ATTR_SCRIPT_NAME = "script_name"

SERVICE_EXECUTE_SCRIPT_SCHEMA = probatio.Schema(
    {
        probatio.Optional(ATTR_CONFIG_ENTRY_ID): ConfigEntrySelector(
            {"integration": XENIA_DOMAIN}
        ),
        probatio.Optional(ATTR_SCRIPT_ID): probatio.All(
            probatio.Coerce(int), probatio.Range(min=1)
        ),
        probatio.Optional(ATTR_SCRIPT_NAME): str,
    }
)


async def _execute_script(call: ServiceCall) -> None:
    entry: XeniaConfigEntry = service.async_get_config_entry(
        call.hass, XENIA_DOMAIN, call.data.get(ATTR_CONFIG_ENTRY_ID)
    )
    runtime = entry.runtime_data
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
    await async_write(
        runtime.coordinator, runtime.coordinator.xenia.execute_script(script_id)
    )


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration's actions."""
    hass.services.async_register(
        XENIA_DOMAIN,
        SERVICE_EXECUTE_SCRIPT,
        _execute_script,
        schema=SERVICE_EXECUTE_SCRIPT_SCHEMA,
    )
