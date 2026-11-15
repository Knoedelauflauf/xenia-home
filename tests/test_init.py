"""Tests for setting up, unloading and removing the integration."""

from datetime import timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.select import (
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_OPTION,
    CONF_HOST,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er
import probatio
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.xenia_home.const import XENIA_DOMAIN

from tests import pass_seconds, setup_integration, setup_second_machine
from tests.conftest import MockXeniaApi

POWER_ON_BEHAVIOR = "select.xenia_espresso_machine_power_on_behavior"
MAC = "aa:bb:cc:dd:ee:ff"


async def _execute_script(hass: HomeAssistant, data: dict[str, Any]) -> None:
    await hass.services.async_call(XENIA_DOMAIN, "execute_script", data, blocking=True)


async def test_unload_and_reload(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The entry unloads cleanly and keeps the action registered."""
    assert await hass.config_entries.async_unload(init_integration.entry_id)
    assert init_integration.state is ConfigEntryState.NOT_LOADED
    assert hass.services.has_service(XENIA_DOMAIN, "execute_script")

    assert await hass.config_entries.async_setup(init_integration.entry_id)
    assert init_integration.state is ConfigEntryState.LOADED


async def test_device(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    init_integration: MockConfigEntry,
) -> None:
    """The device is keyed on the MAC address and shows serial number and firmware."""
    [device] = dr.async_entries_for_config_entry(
        device_registry, init_integration.entry_id
    )
    assert device.identifiers == {(XENIA_DOMAIN, "aa:bb:cc:dd:ee:ff")}
    assert device.connections == {(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff")}
    assert device.manufacturer == "Xenia Espresso GmbH"
    assert device.serial_number == "300200000000"
    assert device.sw_version == "4.255/3.95"


async def test_device_of_old_firmware(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
) -> None:
    """Firmware before 4.159 reports no serial number."""
    mock_xenia_api.use_old_firmware()
    await setup_integration(hass, mock_config_entry)
    [device] = dr.async_entries_for_config_entry(
        device_registry, mock_config_entry.entry_id
    )
    assert device.serial_number is None
    assert device.sw_version == "4.22/3.22"


@pytest.mark.parametrize(
    "fields",
    [
        {"FW_VERSION_MAJOR": None},
        {"ESP_FW_MINOR": None},
        {"FW_VERSION_MAJOR": "3.0"},
        {"ESP_FW_MAJOR": []},
    ],
)
async def test_device_of_unknown_firmware(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    fields: dict[str, object],
) -> None:
    """A missing or malformed version part leaves the firmware version out."""
    mock_xenia_api.set_machine(**fields)
    await setup_integration(hass, mock_config_entry)
    [device] = dr.async_entries_for_config_entry(
        device_registry, mock_config_entry.entry_id
    )
    assert device.sw_version is None


@pytest.mark.parametrize(
    "entity_id",
    [
        "sensor.xenia_espresso_machine_electric_current",
        "select.xenia_espresso_machine_left_switch_left_short",
        "select.xenia_espresso_machine_right_switch_right_long",
    ],
)
async def test_noisy_entities_start_disabled(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    entity_id: str,
) -> None:
    """Raw readings and the switch assignments start disabled."""
    entry = entity_registry.async_get(entity_id)
    assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get(entity_id) is None


async def test_entity_id_change_keeps_the_entity_working(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    init_integration: MockConfigEntry,
) -> None:
    """A renamed entity keeps its state and still reacts to actions."""
    entity_registry.async_update_entity(
        POWER_ON_BEHAVIOR, new_entity_id="select.coffee_steam"
    )
    await hass.async_block_till_done()
    assert hass.states.get(POWER_ON_BEHAVIOR) is None

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: "select.coffee_steam", ATTR_OPTION: "steam_on"},
        blocking=True,
    )
    assert hass.states.get("select.coffee_steam").state == "steam_on"


async def test_setup_drops_options_of_older_releases(
    hass: HomeAssistant, mock_config_entry_factory_with_options
) -> None:
    """Options older releases had are removed; the power on behavior moves to its select."""
    entry = mock_config_entry_factory_with_options(
        {
            "poll_interval_idle": 10.0,
            "ready_threshold": 3.0,
            "power_on_behavior": "steam_on",
            "weight_min": 20.0,
        }
    )
    await setup_integration(hass, entry)
    assert entry.options == {"weight_min": 20.0}
    assert hass.states.get(POWER_ON_BEHAVIOR).state == "steam_on"


def _add_entry_of_an_earlier_release(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    host: str = "xenia.local",
) -> MockConfigEntry:
    """Add an entry keyed on its host, with a device and two renamed entities."""
    entry = MockConfigEntry(
        domain=XENIA_DOMAIN,
        title=host,
        unique_id=host,
        minor_version=1,
        data={CONF_HOST: host},
    )
    entry.add_to_hass(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(XENIA_DOMAIN, host)}
    )
    for domain, unique_id, object_id in (
        ("sensor", f"{host}_brew_group_temperature", "group_temp"),
        ("switch", f"{XENIA_DOMAIN}_power_{host}", "coffee_power"),
    ):
        entity_registry.async_get_or_create(
            domain,
            XENIA_DOMAIN,
            unique_id,
            config_entry=entry,
            device_id=device.id,
            suggested_object_id=object_id,
        )
    return entry


def _ids(
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    entry: MockConfigEntry,
) -> tuple[dict[str, set[tuple[str, str]]], dict[str, str]]:
    """Return the identifiers by device id and the unique ids by entity id."""
    return (
        {
            device.id: device.identifiers
            for device in dr.async_entries_for_config_entry(
                device_registry, entry.entry_id
            )
        },
        {
            entity.entity_id: entity.unique_id
            for entity in er.async_entries_for_config_entry(
                entity_registry, entry.entry_id
            )
        },
    )


async def test_migration_keys_the_machine_on_its_mac(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """An entry keyed on its host keeps its device and entities, now keyed on the MAC."""
    entry = _add_entry_of_an_earlier_release(hass, device_registry, entity_registry)
    [device_id] = _ids(device_registry, entity_registry, entry)[0]

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.unique_id == MAC
    devices, entities = _ids(device_registry, entity_registry, entry)
    assert devices == {device_id: {(XENIA_DOMAIN, MAC)}}
    assert entities["sensor.group_temp"] == f"{MAC}_brew_group_temperature"
    assert entities["switch.coffee_power"] == f"{MAC}_power"
    for entity_id in ("sensor.group_temp", "switch.coffee_power"):
        assert hass.states.get(entity_id).state != STATE_UNAVAILABLE
    assert "sensor.xenia_espresso_machine_brewgroup_temperature" not in entities
    assert "switch.xenia_espresso_machine_power" not in entities


async def test_migration_after_a_host_change_keeps_the_live_entities(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Up to 0.7.0 a host change created new ids; those are the ones migrated.

    The entities left behind under the earlier host stay as they are.
    """
    entry = _add_entry_of_an_earlier_release(hass, device_registry, entity_registry)
    hass.config_entries.async_update_entry(entry, unique_id="old.host")
    stale_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(XENIA_DOMAIN, "old.host")}
    )
    entity_registry.async_get_or_create(
        "sensor",
        XENIA_DOMAIN,
        "old.host_brew_group_temperature",
        config_entry=entry,
        device_id=stale_device.id,
        suggested_object_id="stale_group_temp",
    )
    devices_before = _ids(device_registry, entity_registry, entry)[0]

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.unique_id == MAC
    devices, entities = _ids(device_registry, entity_registry, entry)
    assert entities["sensor.group_temp"] == f"{MAC}_brew_group_temperature"
    assert entities["switch.coffee_power"] == f"{MAC}_power"
    assert entities["sensor.stale_group_temp"] == "old.host_brew_group_temperature"
    assert hass.states.get("sensor.group_temp").state != STATE_UNAVAILABLE
    assert devices.keys() == devices_before.keys()
    assert devices[stale_device.id] == {(XENIA_DOMAIN, "old.host")}
    assert "sensor.xenia_espresso_machine_brewgroup_temperature" not in entities


async def test_migration_waits_for_the_machine(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    mock_xenia_api: MockXeniaApi,
    freezer: FrozenDateTimeFactory,
) -> None:
    """While the machine is offline nothing changes; it migrates once it answers."""
    entry = _add_entry_of_an_earlier_release(hass, device_registry, entity_registry)
    ids_before = _ids(device_registry, entity_registry, entry)
    mock_xenia_api.override("get", "overview_single", exc=OSError())

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert entry.unique_id == "xenia.local"
    assert _ids(device_registry, entity_registry, entry) == ids_before

    mock_xenia_api.restore("get", "overview_single")
    freezer.tick(timedelta(minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert entry.state is ConfigEntryState.LOADED
    assert entry.unique_id == MAC
    devices, entities = _ids(device_registry, entity_registry, entry)
    assert devices.keys() == ids_before[0].keys()
    assert entities["sensor.group_temp"] == f"{MAC}_brew_group_temperature"


async def test_reconfigure_moves_an_entry_waiting_for_migration(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    mock_xenia_api: MockXeniaApi,
) -> None:
    """A machine that moved to another host migrates once the host is reconfigured."""
    entry = _add_entry_of_an_earlier_release(hass, device_registry, entity_registry)
    mock_xenia_api.override("get", "overview_single", exc=OSError())
    mock_xenia_api.for_host("new.host")
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "new.host"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.state is ConfigEntryState.LOADED
    assert entry.data == {CONF_HOST: "new.host"}
    assert entry.unique_id == MAC
    assert _ids(device_registry, entity_registry, entry)[1]["sensor.group_temp"] == (
        f"{MAC}_brew_group_temperature"
    )


async def test_reconfigure_to_a_configured_machine_aborts(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
) -> None:
    """An entry waiting for migration cannot be moved onto a machine set up already."""
    entry = _add_entry_of_an_earlier_release(
        hass, device_registry, entity_registry, host="192.168.1.20"
    )
    mock_xenia_api.for_host("192.168.1.20").override(
        "get", "overview_single", exc=OSError()
    )
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    ids_before = _ids(device_registry, entity_registry, entry)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "xenia.local"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data == {CONF_HOST: "192.168.1.20"}
    assert entry.unique_id == "192.168.1.20"
    assert _ids(device_registry, entity_registry, entry) == ids_before


async def test_migration_of_a_second_entry_for_the_machine_fails(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
) -> None:
    """A machine added twice under different hosts keeps only the first entry working."""
    mock_xenia_api.for_host("192.168.1.20")
    entry = _add_entry_of_an_earlier_release(
        hass, device_registry, entity_registry, host="192.168.1.20"
    )
    ids_before = _ids(device_registry, entity_registry, entry)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.MIGRATION_ERROR
    assert entry.error_reason_translation_key == "duplicate_machine"
    assert entry.unique_id == "192.168.1.20"
    assert _ids(device_registry, entity_registry, entry) == ids_before
    assert init_integration.state is ConfigEntryState.LOADED


async def test_remove_deletes_the_shot_history(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    init_integration: MockConfigEntry,
    poll,
) -> None:
    """Removing the machine deletes its stored shots."""
    for second in range(12):
        await poll(MA_STATUS=3, SCALE_WEIGHT=float(second))
    for _ in range(3):
        await poll(MA_STATUS=1, SCALE_WEIGHT=12.0)
    assert any(key.startswith(f"{XENIA_DOMAIN}/") for key in hass_storage)

    await hass.config_entries.async_remove(init_integration.entry_id)
    await hass.async_block_till_done()
    assert not any(key.startswith(f"{XENIA_DOMAIN}/") for key in hass_storage)


@pytest.mark.parametrize(
    ("data", "script_id"),
    [
        ({"script_id": 10}, 10),
        ({"script_name": "MyShot"}, 10),
        ({"script_name": "Espresso"}, 1),
        ({"script_id": 2, "script_name": "MyShot"}, 2),
    ],
)
async def test_execute_script(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    data: dict[str, Any],
    script_id: int,
) -> None:
    """The action runs a script by id or by name; the id wins."""
    await _execute_script(hass, data)
    assert mock_xenia_api.bodies("post", "scripts/execute") == [f'{{"ID":{script_id}}}']


@pytest.mark.parametrize("script_id", [0, -1])
async def test_execute_script_rejects_ids_below_one(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    script_id: int,
) -> None:
    """Script ids start at 1, as the action's selector shows."""
    with pytest.raises(probatio.Invalid):
        await _execute_script(hass, {"script_id": script_id})
    assert mock_xenia_api.bodies("post", "scripts/execute") == []


async def test_execute_script_polls_the_machine(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The action is followed by a poll a second later, also while idle."""
    mock_xenia_api.set_overview(MA_STATUS=0)
    await setup_integration(hass, mock_config_entry)
    polls = len(mock_xenia_api.bodies("get", "overview"))
    await _execute_script(hass, {"script_id": 10})
    await pass_seconds(hass, freezer, 1)
    assert len(mock_xenia_api.bodies("get", "overview")) > polls


async def test_execute_script_by_a_shared_name(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_xenia_api: MockXeniaApi
) -> None:
    """Scripts sharing a name are run by the name with the id the select shows."""
    mock_xenia_api.set_scripts({12: "Espresso"})
    await hass.config_entries.async_reload(init_integration.entry_id)
    await hass.async_block_till_done()
    await _execute_script(hass, {"script_name": "Espresso (12)"})
    with pytest.raises(ServiceValidationError):
        await _execute_script(hass, {"script_name": "Espresso"})
    assert mock_xenia_api.bodies("post", "scripts/execute") == ['{"ID":12}']


@pytest.mark.parametrize(
    ("data", "translation_key"),
    [
        ({}, "script_required"),
        ({"script_name": "Ghost"}, "script_not_found"),
        (
            {"config_entry_id": "nope", "script_id": 10},
            "service_config_entry_not_found",
        ),
    ],
)
async def test_execute_script_rejects_invalid_calls(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    data: dict[str, Any],
    translation_key: str,
) -> None:
    """Calls without a script, with an unknown script or machine are rejected."""
    with pytest.raises(ServiceValidationError) as exc_info:
        await _execute_script(hass, data)
    assert exc_info.value.translation_key == translation_key


@pytest.mark.parametrize("address", [False, True])
async def test_execute_script_needs_a_loaded_machine(
    hass: HomeAssistant, init_integration: MockConfigEntry, address: bool
) -> None:
    """The action fails while the machine is not loaded."""
    await hass.config_entries.async_unload(init_integration.entry_id)
    data: dict[str, Any] = {"script_id": 10}
    if address:
        data["config_entry_id"] = init_integration.entry_id
    with pytest.raises(ServiceValidationError) as exc_info:
        await _execute_script(hass, data)
    assert exc_info.value.translation_key == "service_config_entry_not_loaded"


async def test_execute_script_with_several_machines(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_xenia_api: MockXeniaApi
) -> None:
    """With several machines the call has to name one, and only that one runs it."""
    second, second_machine = await setup_second_machine(hass, mock_xenia_api)
    with pytest.raises(ServiceValidationError) as exc_info:
        await _execute_script(hass, {"script_id": 10})
    assert (
        exc_info.value.translation_key
        == "service_found_multiple_config_entry_for_domain"
    )

    await _execute_script(hass, {"config_entry_id": second.entry_id, "script_id": 1})
    assert second_machine.bodies("post", "scripts/execute") == ['{"ID":1}']
    assert mock_xenia_api.bodies("post", "scripts/execute") == []


async def test_execute_script_refused_by_machine(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_xenia_api: MockXeniaApi
) -> None:
    """A refused request raises a translated error with the cause."""
    mock_xenia_api.fail("post", "scripts/execute")
    with pytest.raises(HomeAssistantError) as exc_info:
        await _execute_script(hass, {"script_id": 10})
    assert exc_info.value.translation_key == "write_failed"
    assert exc_info.value.translation_placeholders == {
        "error": "ClientResponseError: 500, message='Internal Server Error', "
        "url='http://xenia.local/api/v2/scripts/execute'"
    }
