"""Config flow for the Xenia espresso machine integration."""

import logging
from typing import Any, override

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
)
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
from .migration import MAC_MINOR_VERSION, async_migrate_to_mac
from .script_parser import COMMAND_WEIGHT_TARGET, parse_instruction
from .xenia import Xenia

_LOGGER = logging.getLogger(__name__)

HOST_SCHEMA = probatio.Schema({probatio.Required(CONF_HOST, default=DEFAULT_HOST): str})

CREATE_NEW_SCRIPT = "create_new"
WEIGHT_SELECTOR = NumberSelector(
    NumberSelectorConfig(
        min=0, step="any", unit_of_measurement="g", mode=NumberSelectorMode.BOX
    )
)


async def _async_get_machine_id(hass: HomeAssistant, host: str) -> str | None:
    try:
        mac = await Xenia(host, async_get_clientsession(hass)).get_mac()
    except REQUEST_ERRORS:
        return None
    return format_mac(mac)


class XeniaConfigFlow(ConfigFlow, domain=XENIA_DOMAIN):
    """Add a Xenia machine by host, or change the host of one."""

    VERSION = 1
    MINOR_VERSION = MAC_MINOR_VERSION

    @staticmethod
    @callback
    @override
    def async_get_options_flow(config_entry: ConfigEntry) -> XeniaOptionsFlow:
        """Return the options flow."""
        return XeniaOptionsFlow()

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the host and add the machine."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            if machine_id := await _async_get_machine_id(self.hass, host):
                await self.async_set_unique_id(machine_id)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
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
            if machine_id := await _async_get_machine_id(self.hass, host):
                if entry.minor_version < MAC_MINOR_VERSION:
                    # Its ids still hold the old host, which is about to change.
                    if self.hass.config_entries.async_entry_for_domain_unique_id(
                        XENIA_DOMAIN, machine_id
                    ):
                        return self.async_abort(reason="already_configured")
                    await async_migrate_to_mac(self.hass, entry, machine_id)
                else:
                    await self.async_set_unique_id(machine_id)
                    self._abort_if_unique_id_mismatch()
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
        self._known_script_ids: set[int] = set()

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

        self._known_script_ids = set(scripts)
        options = [SelectOptionDict(value=CREATE_NEW_SCRIPT, label=DEFAULT_SCRIPT_NAME)]
        for script_id, title in scripts.items():
            try:
                script = await xenia.read_script(script_id)
                parsed = parse_instruction(script.get("Content", ""))
            except (*REQUEST_ERRORS, ValueError) as err:
                _LOGGER.debug("Could not read script %s, skipping: %s", script_id, err)
                continue
            if parsed.has_command(COMMAND_WEIGHT_TARGET):
                options.append(SelectOptionDict(value=str(script_id), label=title))

        current = str(self.config_entry.options.get(CONF_MANAGED_SCRIPT_ID))
        schema = probatio.Schema(
            {
                probatio.Required(
                    CONF_MANAGED_SCRIPT_ID,
                    default=current
                    if any(o["value"] == current for o in options)
                    else probatio.UNDEFINED,
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=options, translation_key=CONF_MANAGED_SCRIPT_ID
                    )
                ),
            }
        )
        return self.async_show_form(step_id="select_script", data_schema=schema)

    async def async_step_configure_weight(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set the range and step of the weight target."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input[CONF_WEIGHT_MIN] >= user_input[CONF_WEIGHT_MAX]:
                errors[CONF_WEIGHT_MAX] = "weight_max_not_above_min"
            if user_input[CONF_WEIGHT_STEP] <= 0:
                errors[CONF_WEIGHT_STEP] = "weight_step_not_positive"
        if user_input is not None and not errors:
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
                ): WEIGHT_SELECTOR,
                probatio.Required(
                    CONF_WEIGHT_MAX,
                    default=options.get(CONF_WEIGHT_MAX, DEFAULT_WEIGHT_MAX),
                ): WEIGHT_SELECTOR,
                probatio.Required(
                    CONF_WEIGHT_STEP,
                    default=options.get(CONF_WEIGHT_STEP, DEFAULT_WEIGHT_STEP),
                ): WEIGHT_SELECTOR,
            }
        )
        return self.async_show_form(
            step_id="configure_weight",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    async def _async_create_script(self) -> ConfigFlowResult:
        xenia = self._xenia()
        try:
            await xenia.create_script(DEFAULT_SCRIPT_NAME, DEFAULT_SCRIPT_INSTRUCTION)
            scripts = await xenia.get_scripts()
        except REQUEST_ERRORS:
            return self.async_abort(reason="cannot_connect")

        # The create endpoint does not return the id of the new script.
        new_id = next(
            (
                script_id
                for script_id, title in scripts.items()
                if title == DEFAULT_SCRIPT_NAME
                and script_id not in self._known_script_ids
            ),
            None,
        )
        if new_id is None:
            return self.async_abort(reason="script_not_created")

        self._managed_script_id = new_id
        return await self.async_step_configure_weight()
