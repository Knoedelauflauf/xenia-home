"""Base entity for the Xenia espresso machine."""

from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import XENIA_DOMAIN
from .coordinator import XeniaConfigEntry, XeniaDataUpdateCoordinator, XeniaRuntimeData
from .xenia import XeniaMachineData


def machine_id(entry: XeniaConfigEntry) -> str:
    """Return the key of the machine's device and entity unique ids.

    This is the host the machine was added with. It is kept when the host is
    reconfigured, so the ids stay stable.
    """
    assert entry.unique_id is not None
    return entry.unique_id


def build_device_info(
    entry: XeniaConfigEntry, machine: XeniaMachineData, mac: str | None = None
) -> DeviceInfo:
    """Build the device info of the machine."""
    fw_version = machine.fw_version()
    esp_fw_version = machine.esp_fw_version()
    info = DeviceInfo(
        identifiers={(XENIA_DOMAIN, machine_id(entry))},
        name="Xenia Espresso Machine",
        manufacturer="Xenia Espresso GmbH",
        model="DBL",
        sw_version=(
            f"{fw_version}/{esp_fw_version}" if fw_version and esp_fw_version else None
        ),
        serial_number=machine.ma_sn,
    )
    if mac:
        info["connections"] = {(CONNECTION_NETWORK_MAC, mac)}
    return info


class XeniaEntity(CoordinatorEntity[XeniaDataUpdateCoordinator]):
    """Entity of the machine, updated by both coordinators."""

    _attr_has_entity_name = True

    async def async_added_to_hass(self) -> None:
        """Also listen to the config coordinator."""
        await super().async_added_to_hass()
        # A coordinator only polls while it has listeners.
        self.async_on_remove(
            self.runtime_data.config_coordinator.async_add_listener(
                self.async_write_ha_state
            )
        )

    @callback
    def async_entity_id_changed(self, old_entity_id: str) -> None:
        """Keep the entity when its entity_id changes; nothing is keyed on it."""
        # Called from Home Assistant 2026.11 on, which added the hook.
        super().async_entity_id_changed(old_entity_id)  # type: ignore[misc]

    @property
    def machine_id(self) -> str:
        """Return the key of the machine's unique ids."""
        return machine_id(self.coordinator.config_entry)

    @property
    def runtime_data(self) -> XeniaRuntimeData:
        """Return the runtime data of the config entry."""
        return self.coordinator.config_entry.runtime_data

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info of the machine."""
        return build_device_info(
            self.coordinator.config_entry,
            self.runtime_data.config_coordinator.data.machine,
            self.coordinator.data.overview_single.ma_mac,
        )
