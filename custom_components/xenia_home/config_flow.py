import asyncio
from typing import Any

from aiohttp import ClientError
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DEFAULT_HOST, XENIA_DOMAIN
from .xenia import Xenia

DATA_SCHEMA_USER = vol.Schema(
    {
        vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
    }
)


class XeniaConfigFlow(ConfigFlow, domain=XENIA_DOMAIN):
    VERSION = 1

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
