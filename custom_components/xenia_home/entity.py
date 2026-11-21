"""Base entity for the Xenia espresso machine."""

from typing import Any, override

from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import XENIA_DOMAIN
from .coordinator import (
    XeniaConfigEntry,
    XeniaCoordinator,
    XeniaDataUpdateCoordinator,
    XeniaRuntimeData,
)
from .xenia import XeniaMachineData


def machine_id(entry: XeniaConfigEntry) -> str:
    """Return the key of the machine's device and entity unique ids.

    This is the config entry's unique id, the MAC address of the machine.
    """
    assert entry.unique_id is not None
    return entry.unique_id


def build_device_info(entry: XeniaConfigEntry, machine: XeniaMachineData) -> DeviceInfo:
    """Build the device info of the machine."""
    versions = (
        machine.fw_version_major,
        machine.fw_version_minor,
        machine.esp_fw_major,
        machine.esp_fw_minor,
    )
    return DeviceInfo(
        identifiers={(XENIA_DOMAIN, machine_id(entry))},
        connections={(CONNECTION_NETWORK_MAC, machine_id(entry))},
        name="Xenia Espresso Machine",
        manufacturer="Xenia Espresso GmbH",
        model="DBL",
        sw_version=None if None in versions else "{}.{}/{}.{}".format(*versions),
        serial_number=machine.ma_sn,
    )


class XeniaEntity[CoordinatorT: XeniaCoordinator[Any] = XeniaDataUpdateCoordinator](
    CoordinatorEntity[CoordinatorT]
):
    """Entity of the machine, also updated by the config coordinator."""

    _attr_has_entity_name = True

    @override
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
    @override
    def async_entity_id_changed(self, old_entity_id: str) -> None:  # type: ignore[misc,unused-ignore]
        """Keep the entity when its entity_id changes; nothing is keyed on it."""
        # Called from Home Assistant 2026.11 on, which added the hook.
        super().async_entity_id_changed(old_entity_id)  # type: ignore[misc,unused-ignore]

    @property
    def machine_id(self) -> str:
        """Return the key of the machine's unique ids."""
        return machine_id(self.coordinator.config_entry)

    @property
    def runtime_data(self) -> XeniaRuntimeData:
        """Return the runtime data of the config entry."""
        return self.coordinator.config_entry.runtime_data

    @property
    @override
    def device_info(self) -> DeviceInfo:
        """Return the device info of the machine."""
        return build_device_info(
            self.coordinator.config_entry,
            self.runtime_data.config_coordinator.data.machine,
        )
