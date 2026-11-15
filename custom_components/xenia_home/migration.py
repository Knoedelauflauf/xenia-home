"""Move entries of releases up to 0.7.0 from their host to the machine's MAC."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import XENIA_DOMAIN

MAC_MINOR_VERSION = 2


async def async_migrate_to_mac(
    hass: HomeAssistant, entry: ConfigEntry, mac: str
) -> None:
    """Re-key the entry, its device and its entities from the host to `mac`.

    Up to 0.7.0 the ids were built from the current host, so after a host
    change the entities of the earlier host are left behind; they stay as
    they are.
    """
    host = entry.data[CONF_HOST]

    @callback
    def migrate_unique_id(entity: er.RegistryEntry) -> dict[str, str] | None:
        unique_id = entity.unique_id
        prefix, suffix = f"{XENIA_DOMAIN}_", f"_{host}"
        if unique_id.startswith(prefix) and unique_id.endswith(suffix):
            key = unique_id.removeprefix(prefix).removesuffix(suffix)
            return {"new_unique_id": f"{mac}_{key}"}
        if unique_id.startswith(f"{host}_"):
            return {"new_unique_id": f"{mac}{unique_id.removeprefix(host)}"}
        return None

    await er.async_migrate_entries(hass, entry.entry_id, migrate_unique_id)
    device_registry = dr.async_get(hass)
    if device := device_registry.async_get_device_by_identifier(
        (XENIA_DOMAIN, host), entry.entry_id
    ):
        device_registry.async_update_device(
            device.id, new_identifiers={(XENIA_DOMAIN, mac)}
        )
    hass.config_entries.async_update_entry(
        entry, unique_id=mac, minor_version=MAC_MINOR_VERSION
    )
