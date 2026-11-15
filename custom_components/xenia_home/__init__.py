"""Xenia Espresso Machine integration."""

from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
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
from .entity import machine_id
from .errors import REQUEST_ERRORS, describe_error
from .recorder_import import async_import_recorder_shots
from .services import async_setup_services
from .shot_store import XeniaShotStore
from .websocket import async_register_commands
from .xenia import Xenia

CONFIG_SCHEMA = cv.config_entry_only_config_schema(XENIA_DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration's actions and websocket commands."""
    async_register_commands(hass)
    async_setup_services(hass)
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: XeniaConfigEntry) -> bool:
    """Key the entry, its device and its entities on the machine's MAC address."""
    if entry.minor_version < 2:
        xenia = Xenia(entry.data[CONF_HOST], async_get_clientsession(hass))
        try:
            mac = await xenia.get_mac()
        except REQUEST_ERRORS as err:
            raise ConfigEntryNotReady(
                translation_domain=XENIA_DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": describe_error(err)},
            ) from err
        old_id, new_id = machine_id(entry), dr.format_mac(mac)
        if other := hass.config_entries.async_entry_for_domain_unique_id(
            XENIA_DOMAIN, new_id
        ):
            raise ConfigEntryError(
                translation_domain=XENIA_DOMAIN,
                translation_key="duplicate_machine",
                translation_placeholders={"title": other.title},
            )

        @callback
        def migrate_unique_id(entity: er.RegistryEntry) -> dict[str, str]:
            # Ids with the domain prefix end in the host, all others start with it.
            if entity.unique_id.startswith(f"{XENIA_DOMAIN}_"):
                prefix = entity.unique_id.removesuffix(old_id)
                return {"new_unique_id": f"{prefix}{new_id}"}
            suffix = entity.unique_id.removeprefix(old_id)
            return {"new_unique_id": f"{new_id}{suffix}"}

        await er.async_migrate_entries(hass, entry.entry_id, migrate_unique_id)
        device_registry = dr.async_get(hass)
        if device := device_registry.async_get_device_by_identifier(
            (XENIA_DOMAIN, old_id), entry.entry_id
        ):
            device_registry.async_update_device(
                device.id, new_identifiers={(XENIA_DOMAIN, new_id)}
            )
        hass.config_entries.async_update_entry(entry, unique_id=new_id, minor_version=2)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: XeniaConfigEntry) -> bool:
    """Set up Xenia from a config entry."""
    xenia = Xenia(entry.data[CONF_HOST], async_get_clientsession(hass))

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
    options = {k: v for k, v in entry.options.items() if k not in REMOVED_OPTION_KEYS}
    if (
        value := options.pop(CONF_POWER_ON_BEHAVIOR, None)
    ) in POWER_ON_BEHAVIOR_OPTIONS:
        entry.runtime_data.power_on_behavior = PowerOnBehavior(value)
    if options != entry.options:
        hass.config_entries.async_update_entry(entry, options=options)

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
