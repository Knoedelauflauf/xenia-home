import asyncio
import logging
from typing import Any

from aiohttp import ClientError
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

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
from .script_parser import COMMAND_WEIGHT_TARGET, parse_instruction
from .xenia import Xenia

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA_USER = vol.Schema(
    {
        vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
    }
)


CREATE_NEW_SCRIPT = "__create_new__"


class XeniaConfigFlow(ConfigFlow, domain=XENIA_DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return XeniaOptionsFlow()

    def __init__(self) -> None:
        self._entry: ConfigEntry | None = None
        self._host: str | None = None
        self._name: str | None = None

    async def _async_test_connection(
        self, hass: HomeAssistant, host: str
    ) -> str | None:
        session = async_get_clientsession(hass)
        xenia = Xenia(host, session)
        try:
            if not await asyncio.wait_for(xenia.device_connected(), timeout=8):
                return "cannot_connect"
            return None
        except (TimeoutError, ClientError, OSError):
            return "cannot_connect"

    def _create_entry(self, title: str) -> ConfigFlowResult:
        assert self._host is not None
        return self.async_create_entry(
            title=title,
            data={CONF_HOST: self._host},
        )

    async def _update_entry(self) -> None:
        assert self._entry is not None
        assert self._host is not None
        self.hass.config_entries.async_update_entry(
            self._entry,
            data={
                CONF_HOST: self._host,
            },
        )
        await self.hass.config_entries.async_reload(self._entry.entry_id)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._host = user_input[CONF_HOST]
            self._name = str(user_input[CONF_HOST])

            await self.async_set_unique_id(self._host)
            self._abort_if_unique_id_configured()
            error = await self._async_test_connection(self.hass, self._host)
            if error is None:
                return self._create_entry(self._name)

            errors["base"] = error

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA_USER, errors=errors
        )

    async def async_step_reconfigure(
        self, _: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        assert entry is not None
        self._entry = entry
        self._host = entry.data.get(CONF_HOST, DEFAULT_HOST)
        self._name = entry.title or self._host

        return await self.async_step_reconfigure_confirm()

    async def async_step_reconfigure_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._host is not None
        errors: dict[str, str] = {}

        schema = vol.Schema({vol.Required(CONF_HOST, default=self._host): str})

        if user_input is not None:
            new_host = user_input[CONF_HOST].strip()
            error = await self._async_test_connection(self.hass, new_host)
            if error is None:
                self._host = new_host
                await self._update_entry()
                return self.async_abort(reason="reconfigure_successful")
            errors["base"] = error

        return self.async_show_form(
            step_id="reconfigure_confirm",
            data_schema=schema,
            description_placeholders={"name": self._name or self._host},
            errors=errors,
        )


class XeniaOptionsFlow(OptionsFlow):
    """Options flow for Xenia weight management."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            if not user_input.get(CONF_WEIGHT_MANAGEMENT_ENABLED):
                # Disable weight management
                return self.async_create_entry(
                    data={
                        **self.config_entry.options,
                        CONF_WEIGHT_MANAGEMENT_ENABLED: False,
                        CONF_MANAGED_SCRIPT_ID: None,
                    },
                )
            # Enabled — proceed to script selection
            return await self.async_step_select_script()

        current = self.config_entry.options.get(CONF_WEIGHT_MANAGEMENT_ENABLED, False)
        schema = vol.Schema(
            {vol.Required(CONF_WEIGHT_MANAGEMENT_ENABLED, default=current): bool}
        )
        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_select_script(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            selected = user_input[CONF_MANAGED_SCRIPT_ID]
            if selected == CREATE_NEW_SCRIPT:
                return await self._create_new_script()
            self._managed_script_id = int(selected)
            return await self.async_step_configure_weight()

        # Build list of scripts that contain a weight command
        host = self.config_entry.data[CONF_HOST]
        session = async_get_clientsession(self.hass)
        xenia = Xenia(host, session)

        try:
            all_scripts = await xenia.get_scripts()
        except (ClientError, OSError, TimeoutError):
            return self.async_abort(reason="cannot_connect")

        weight_scripts: dict[str, str] = {}
        for script_id, title in all_scripts.items():
            try:
                script_data = await xenia.read_script(script_id)
                instruction = script_data.get("Content", "")
                parsed = parse_instruction(instruction)
                if parsed.has_command(COMMAND_WEIGHT_TARGET):
                    weight_scripts[str(script_id)] = title
            except (ClientError, OSError, TimeoutError):
                _LOGGER.debug("Could not read script %s, skipping", script_id)

        options: dict[str, str] = {}
        # Pre-select current managed script if set
        current_id = self.config_entry.options.get(CONF_MANAGED_SCRIPT_ID)
        for sid, title in weight_scripts.items():
            options[sid] = title
        options[CREATE_NEW_SCRIPT] = DEFAULT_SCRIPT_NAME + " (create new)"

        default = str(current_id) if current_id and str(current_id) in options else None

        schema = vol.Schema(
            {
                vol.Required(CONF_MANAGED_SCRIPT_ID, default=default): vol.In(options),
            }
        )
        return self.async_show_form(step_id="select_script", data_schema=schema)

    async def async_step_configure_weight(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure weight target min, max, and step size."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    **self.config_entry.options,
                    CONF_WEIGHT_MANAGEMENT_ENABLED: True,
                    CONF_MANAGED_SCRIPT_ID: self._managed_script_id,
                    CONF_WEIGHT_MIN: user_input[CONF_WEIGHT_MIN],
                    CONF_WEIGHT_MAX: user_input[CONF_WEIGHT_MAX],
                    CONF_WEIGHT_STEP: user_input[CONF_WEIGHT_STEP],
                },
            )

        current_min = self.config_entry.options.get(CONF_WEIGHT_MIN, DEFAULT_WEIGHT_MIN)
        current_max = self.config_entry.options.get(CONF_WEIGHT_MAX, DEFAULT_WEIGHT_MAX)
        current_step = self.config_entry.options.get(
            CONF_WEIGHT_STEP, DEFAULT_WEIGHT_STEP
        )

        schema = vol.Schema(
            {
                vol.Required(CONF_WEIGHT_MIN, default=current_min): vol.Coerce(float),
                vol.Required(CONF_WEIGHT_MAX, default=current_max): vol.Coerce(float),
                vol.Required(CONF_WEIGHT_STEP, default=current_step): vol.Coerce(float),
            }
        )
        return self.async_show_form(step_id="configure_weight", data_schema=schema)

    async def _create_new_script(self) -> ConfigFlowResult:
        """Create a new script on the machine and store its ID."""
        host = self.config_entry.data[CONF_HOST]
        session = async_get_clientsession(self.hass)
        xenia = Xenia(host, session)

        try:
            await xenia.create_script(DEFAULT_SCRIPT_NAME, DEFAULT_SCRIPT_INSTRUCTION)
            # Re-fetch script list to find the newly created script
            scripts = await xenia.get_scripts()
        except (ClientError, OSError, TimeoutError):
            return self.async_abort(reason="cannot_connect")

        # Find the new script by name
        new_id: int | None = None
        for sid, title in scripts.items():
            if title == DEFAULT_SCRIPT_NAME:
                new_id = sid
                break

        if new_id is None:
            _LOGGER.error(
                "Created script '%s' but could not find it", DEFAULT_SCRIPT_NAME
            )
            return self.async_abort(reason="cannot_connect")

        self._managed_script_id = new_id
        return await self.async_step_configure_weight()
