"""Config flow for the Xenia espresso machine integration."""

import asyncio
import logging
from typing import Any

from aiohttp import ClientError
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)
import voluptuous as vol

from .const import (
    CONF_CONFIGURE_POLLING,
    CONF_MANAGED_SCRIPT_ID,
    CONF_POLL_ACTIVE,
    CONF_POLL_BREWING,
    CONF_POLL_IDLE,
    CONF_POLL_READY,
    CONF_READY_THRESHOLD,
    CONF_SHOT_TIMER_IDLE_RESET,
    CONF_SHOT_TIMER_START_PRESSURE,
    CONF_WEIGHT_MANAGEMENT_ENABLED,
    CONF_WEIGHT_MAX,
    CONF_WEIGHT_MIN,
    CONF_WEIGHT_STEP,
    DEFAULT_HOST,
    DEFAULT_POLL_ACTIVE,
    DEFAULT_POLL_BREWING,
    DEFAULT_POLL_IDLE,
    DEFAULT_POLL_READY,
    DEFAULT_READY_THRESHOLD,
    DEFAULT_SCRIPT_INSTRUCTION,
    DEFAULT_SCRIPT_NAME,
    DEFAULT_SHOT_TIMER_IDLE_RESET,
    DEFAULT_SHOT_TIMER_START_PRESSURE,
    DEFAULT_WEIGHT_MAX,
    DEFAULT_WEIGHT_MIN,
    DEFAULT_WEIGHT_STEP,
    POLLING_OPTION_KEYS,
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
    """User-driven config flow for adding and reconfiguring a Xenia machine."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler for this integration."""
        return XeniaOptionsFlow()

    def __init__(self) -> None:
        """Initialize per-flow state."""
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
        except TimeoutError, ClientError, OSError:
            return "cannot_connect"
        return None

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
        """Handle the initial step where the user supplies the host."""
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
        """Pre-fill the existing host and forward to the reconfigure form."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        assert entry is not None
        self._entry = entry
        self._host = entry.data.get(CONF_HOST, DEFAULT_HOST)
        self._name = entry.title or self._host

        return await self.async_step_reconfigure_confirm()

    async def async_step_reconfigure_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate a new host and update the existing entry."""
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
    """Options flow for Xenia weight management and polling configuration."""

    _MIN_POLL_INTERVAL = 0.5

    def __init__(self) -> None:
        """Initialize options flow."""
        super().__init__()
        self._configure_polling: bool = False
        self._managed_script_id: int | None = None
        self._weight_data: dict[str, Any] = {}
        self._shot_timer_idle_reset: int = DEFAULT_SHOT_TIMER_IDLE_RESET
        self._shot_timer_start_pressure: float = DEFAULT_SHOT_TIMER_START_PRESSURE

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the options entry form and route to weight or polling flow."""
        if user_input is not None:
            self._configure_polling = user_input.get(CONF_CONFIGURE_POLLING, False)
            self._shot_timer_idle_reset = user_input[CONF_SHOT_TIMER_IDLE_RESET]
            self._shot_timer_start_pressure = user_input[CONF_SHOT_TIMER_START_PRESSURE]
            if not user_input.get(CONF_WEIGHT_MANAGEMENT_ENABLED):
                # Disable weight management — strip polling keys if toggle off
                self._weight_data = {
                    CONF_WEIGHT_MANAGEMENT_ENABLED: False,
                    CONF_MANAGED_SCRIPT_ID: None,
                }
                if not self._configure_polling:
                    new_data = {
                        **self.config_entry.options,
                        **self._weight_data,
                        CONF_SHOT_TIMER_IDLE_RESET: self._shot_timer_idle_reset,
                        CONF_SHOT_TIMER_START_PRESSURE: self._shot_timer_start_pressure,
                    }
                    for key in POLLING_OPTION_KEYS:
                        new_data.pop(key, None)
                    return self.async_create_entry(data=new_data)
                return await self.async_step_configure_polling()
            # Enabled — proceed to script selection
            return await self.async_step_select_script()

        current_weight = self.config_entry.options.get(
            CONF_WEIGHT_MANAGEMENT_ENABLED, False
        )
        # Default the polling toggle to True if any polling key already exists
        current_polling = any(
            key in self.config_entry.options for key in POLLING_OPTION_KEYS
        )
        current_shot_timer_idle_reset = self.config_entry.options.get(
            CONF_SHOT_TIMER_IDLE_RESET, DEFAULT_SHOT_TIMER_IDLE_RESET
        )
        current_shot_timer_start_pressure = self.config_entry.options.get(
            CONF_SHOT_TIMER_START_PRESSURE, DEFAULT_SHOT_TIMER_START_PRESSURE
        )
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_WEIGHT_MANAGEMENT_ENABLED, default=current_weight
                ): bool,
                vol.Required(
                    CONF_SHOT_TIMER_START_PRESSURE,
                    default=current_shot_timer_start_pressure,
                ): vol.All(
                    NumberSelector(
                        NumberSelectorConfig(
                            min=0,
                            step=0.1,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement="bar",
                        )
                    ),
                    vol.Coerce(float),
                ),
                vol.Required(
                    CONF_SHOT_TIMER_IDLE_RESET,
                    default=current_shot_timer_idle_reset,
                ): vol.All(
                    NumberSelector(
                        NumberSelectorConfig(
                            min=0,
                            step=1,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement="s",
                        )
                    ),
                    vol.Coerce(int),
                ),
                vol.Required(CONF_CONFIGURE_POLLING, default=current_polling): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_select_script(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick an existing weight-script or create a new one."""
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
        except ClientError, OSError, TimeoutError:
            return self.async_abort(reason="cannot_connect")

        weight_scripts: dict[str, str] = {}
        for script_id, title in all_scripts.items():
            try:
                script_data = await xenia.read_script(script_id)
                instruction = script_data.get("Content", "")
                parsed = parse_instruction(instruction)
                if parsed.has_command(COMMAND_WEIGHT_TARGET):
                    weight_scripts[str(script_id)] = title
            except ClientError, OSError, TimeoutError:
                _LOGGER.debug("Could not read script %s, skipping", script_id)

        current_id = self.config_entry.options.get(CONF_MANAGED_SCRIPT_ID)
        options: dict[str, str] = dict(weight_scripts)
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
            self._weight_data = {
                CONF_WEIGHT_MANAGEMENT_ENABLED: True,
                CONF_MANAGED_SCRIPT_ID: self._managed_script_id,
                CONF_WEIGHT_MIN: user_input[CONF_WEIGHT_MIN],
                CONF_WEIGHT_MAX: user_input[CONF_WEIGHT_MAX],
                CONF_WEIGHT_STEP: user_input[CONF_WEIGHT_STEP],
            }
            if self._configure_polling:
                return await self.async_step_configure_polling()
            new_data = {
                **self.config_entry.options,
                **self._weight_data,
                CONF_SHOT_TIMER_IDLE_RESET: self._shot_timer_idle_reset,
                CONF_SHOT_TIMER_START_PRESSURE: self._shot_timer_start_pressure,
            }
            for key in POLLING_OPTION_KEYS:
                new_data.pop(key, None)
            return self.async_create_entry(data=new_data)

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

    async def async_step_configure_polling(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure per-state polling intervals."""
        if user_input is not None:
            polling_data = {
                CONF_POLL_BREWING: user_input[CONF_POLL_BREWING],
                CONF_POLL_ACTIVE: user_input[CONF_POLL_ACTIVE],
                CONF_POLL_READY: user_input[CONF_POLL_READY],
                CONF_POLL_IDLE: user_input[CONF_POLL_IDLE],
                CONF_READY_THRESHOLD: user_input[CONF_READY_THRESHOLD],
            }
            new_data = {
                **self.config_entry.options,
                **self._weight_data,
                CONF_SHOT_TIMER_IDLE_RESET: self._shot_timer_idle_reset,
                CONF_SHOT_TIMER_START_PRESSURE: self._shot_timer_start_pressure,
                **polling_data,
            }
            return self.async_create_entry(data=new_data)

        opts = self.config_entry.options
        poll_validator = vol.All(
            vol.Coerce(float), vol.Range(min=self._MIN_POLL_INTERVAL)
        )
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_POLL_BREWING,
                    default=opts.get(CONF_POLL_BREWING, DEFAULT_POLL_BREWING),
                ): poll_validator,
                vol.Required(
                    CONF_POLL_ACTIVE,
                    default=opts.get(CONF_POLL_ACTIVE, DEFAULT_POLL_ACTIVE),
                ): poll_validator,
                vol.Required(
                    CONF_POLL_READY,
                    default=opts.get(CONF_POLL_READY, DEFAULT_POLL_READY),
                ): poll_validator,
                vol.Required(
                    CONF_POLL_IDLE,
                    default=opts.get(CONF_POLL_IDLE, DEFAULT_POLL_IDLE),
                ): poll_validator,
                vol.Required(
                    CONF_READY_THRESHOLD,
                    default=opts.get(CONF_READY_THRESHOLD, DEFAULT_READY_THRESHOLD),
                ): vol.All(vol.Coerce(float), vol.Range(min=0)),
            }
        )
        return self.async_show_form(step_id="configure_polling", data_schema=schema)

    async def _create_new_script(self) -> ConfigFlowResult:
        """Create a new script on the machine and store its ID."""
        host = self.config_entry.data[CONF_HOST]
        session = async_get_clientsession(self.hass)
        xenia = Xenia(host, session)

        try:
            await xenia.create_script(DEFAULT_SCRIPT_NAME, DEFAULT_SCRIPT_INSTRUCTION)
            # Re-fetch script list to find the newly created script
            scripts = await xenia.get_scripts()
        except ClientError, OSError, TimeoutError:
            return self.async_abort(reason="cannot_connect")

        # Find the new script by name
        new_id = next(
            (sid for sid, title in scripts.items() if title == DEFAULT_SCRIPT_NAME),
            None,
        )

        if new_id is None:
            _LOGGER.error(
                "Created script '%s' but could not find it", DEFAULT_SCRIPT_NAME
            )
            return self.async_abort(reason="cannot_connect")

        self._managed_script_id = new_id
        return await self.async_step_configure_weight()
