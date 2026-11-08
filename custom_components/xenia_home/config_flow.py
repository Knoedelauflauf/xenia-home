"""Config flow for the Xenia espresso machine integration."""

import logging
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import probatio

from .const import (
    CONF_MANAGED_SCRIPT_ID,
    CONF_WEIGHT_MANAGEMENT_ENABLED,
    CONF_WEIGHT_MAX,
    CONF_WEIGHT_MIN,
    CONF_WEIGHT_STEP,
    DEFAULT_HOST,
    DEFAULT_SCRIPT_INSTRUCTION,
    DEFAULT_SCRIPT_NAME,
    DEFAULT_WEIGHT_MAX,
    DEFAULT_WEIGHT_MIN,
    DEFAULT_WEIGHT_STEP,
    XENIA_DOMAIN,
)
from .errors import REQUEST_ERRORS
from .script_parser import COMMAND_WEIGHT_TARGET, parse_instruction
from .xenia import Xenia

_LOGGER = logging.getLogger(__name__)

HOST_SCHEMA = probatio.Schema({probatio.Required(CONF_HOST, default=DEFAULT_HOST): str})

CREATE_NEW_SCRIPT = "__create_new__"


async def _async_can_connect(hass: HomeAssistant, host: str) -> bool:
    return await Xenia(host, async_get_clientsession(hass)).device_connected()


class XeniaConfigFlow(ConfigFlow, domain=XENIA_DOMAIN):
    """Add a Xenia machine by host, or change the host of one."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> XeniaOptionsFlow:
        """Return the options flow."""
        return XeniaOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the host and add the machine."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()
            if await _async_can_connect(self.hass, host):
                return self.async_create_entry(title=host, data={CONF_HOST: host})
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(HOST_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the host of the machine."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            if await _async_can_connect(self.hass, host):
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_HOST: host}
                )
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                HOST_SCHEMA, user_input or entry.data
            ),
            description_placeholders={"name": entry.title},
            errors=errors,
        )


class XeniaOptionsFlow(OptionsFlowWithReload):
    """Set up weight management on a script of the machine."""

    def __init__(self) -> None:
        """Initialize the options flow."""
        self._managed_script_id: int | None = None

    def _xenia(self) -> Xenia:
        return Xenia(
            self.config_entry.data[CONF_HOST], async_get_clientsession(self.hass)
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Turn weight management on or off."""
        if user_input is not None:
            if user_input[CONF_WEIGHT_MANAGEMENT_ENABLED]:
                return await self.async_step_select_script()
            return self.async_create_entry(
                data={
                    **self.config_entry.options,
                    CONF_WEIGHT_MANAGEMENT_ENABLED: False,
                    CONF_MANAGED_SCRIPT_ID: None,
                }
            )

        schema = probatio.Schema(
            {
                probatio.Required(
                    CONF_WEIGHT_MANAGEMENT_ENABLED,
                    default=self.config_entry.options.get(
                        CONF_WEIGHT_MANAGEMENT_ENABLED, False
                    ),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_select_script(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a script with a weight target, or create one."""
        if user_input is not None:
            selected = user_input[CONF_MANAGED_SCRIPT_ID]
            if selected == CREATE_NEW_SCRIPT:
                return await self._async_create_script()
            self._managed_script_id = int(selected)
            return await self.async_step_configure_weight()

        xenia = self._xenia()
        try:
            scripts = await xenia.get_scripts()
        except REQUEST_ERRORS:
            return self.async_abort(reason="cannot_connect")

        options: dict[str, str] = {}
        for script_id, title in scripts.items():
            try:
                script = await xenia.read_script(script_id)
            except REQUEST_ERRORS:
                _LOGGER.debug("Could not read script %s, skipping", script_id)
                continue
            if parse_instruction(script.get("Content", "")).has_command(
                COMMAND_WEIGHT_TARGET
            ):
                options[str(script_id)] = title
        options[CREATE_NEW_SCRIPT] = f"{DEFAULT_SCRIPT_NAME} (create new)"

        current = str(self.config_entry.options.get(CONF_MANAGED_SCRIPT_ID))
        schema = probatio.Schema(
            {
                probatio.Required(
                    CONF_MANAGED_SCRIPT_ID,
                    default=current if current in options else probatio.UNDEFINED,
                ): probatio.In(options),
            }
        )
        return self.async_show_form(step_id="select_script", data_schema=schema)

    async def async_step_configure_weight(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set the range and step of the weight target."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    **self.config_entry.options,
                    **user_input,
                    CONF_WEIGHT_MANAGEMENT_ENABLED: True,
                    CONF_MANAGED_SCRIPT_ID: self._managed_script_id,
                }
            )

        options = self.config_entry.options
        schema = probatio.Schema(
            {
                probatio.Required(
                    CONF_WEIGHT_MIN,
                    default=options.get(CONF_WEIGHT_MIN, DEFAULT_WEIGHT_MIN),
                ): probatio.Coerce(float),
                probatio.Required(
                    CONF_WEIGHT_MAX,
                    default=options.get(CONF_WEIGHT_MAX, DEFAULT_WEIGHT_MAX),
                ): probatio.Coerce(float),
                probatio.Required(
                    CONF_WEIGHT_STEP,
                    default=options.get(CONF_WEIGHT_STEP, DEFAULT_WEIGHT_STEP),
                ): probatio.Coerce(float),
            }
        )
        return self.async_show_form(step_id="configure_weight", data_schema=schema)

    async def _async_create_script(self) -> ConfigFlowResult:
        xenia = self._xenia()
        try:
            await xenia.create_script(DEFAULT_SCRIPT_NAME, DEFAULT_SCRIPT_INSTRUCTION)
            scripts = await xenia.get_scripts()
        except REQUEST_ERRORS:
            return self.async_abort(reason="cannot_connect")

        # The create endpoint does not return the id of the new script.
        new_id = next(
            (sid for sid, title in scripts.items() if title == DEFAULT_SCRIPT_NAME),
            None,
        )
        if new_id is None:
            return self.async_abort(reason="script_not_created")

        self._managed_script_id = new_id
        return await self.async_step_configure_weight()
