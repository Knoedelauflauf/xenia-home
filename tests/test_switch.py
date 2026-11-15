"""Tests for the power, eco and steam boiler switches."""

from homeassistant.components.select import (
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_OPTION,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from syrupy.assertion import SnapshotAssertion

from custom_components.xenia_home.const import PowerOnBehavior
from custom_components.xenia_home.xenia import MachineStatus

from tests import setup_integration
from tests.conftest import MockXeniaApi

POWER = "switch.xenia_espresso_machine_power"
ECO = "switch.xenia_espresso_machine_eco_mode"
STEAM_BOILER = "switch.xenia_espresso_machine_steam_boiler_power"
POWER_ON_BEHAVIOR = "select.xenia_espresso_machine_power_on_behavior"
TURN_ON = '{"action":"1"}'
TURN_ON_WITHOUT_STEAM = '{"action":"5"}'


async def _switch(hass: HomeAssistant, service: str, entity_id: str) -> None:
    await hass.services.async_call(
        SWITCH_DOMAIN, service, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )


async def _setup_with_status(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    machine: MockXeniaApi,
    status: MachineStatus,
    **fields,
) -> None:
    machine.set_overview(MA_STATUS=int(status), **fields)
    await setup_integration(hass, entry)


async def test_switch_entities_snapshot(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
) -> None:
    """The switches match the snapshot."""
    for entity_id in (POWER, ECO, STEAM_BOILER):
        assert hass.states.get(entity_id) == snapshot(name=f"{entity_id}-state")
        assert entity_registry.async_get(entity_id) == snapshot(
            name=f"{entity_id}-registry"
        )


@pytest.mark.parametrize(
    ("status", "power", "eco", "steam_boiler"),
    [
        (MachineStatus.ON, STATE_ON, STATE_OFF, STATE_ON),
        (MachineStatus.BREWING, STATE_ON, STATE_OFF, STATE_ON),
        (MachineStatus.DRAINING, STATE_ON, STATE_OFF, STATE_ON),
        (MachineStatus.ECO, STATE_OFF, STATE_ON, STATE_UNAVAILABLE),
        (MachineStatus.OFF, STATE_OFF, STATE_UNAVAILABLE, STATE_UNAVAILABLE),
        (MachineStatus.UNKNOWN, STATE_OFF, STATE_UNAVAILABLE, STATE_UNAVAILABLE),
    ],
)
async def test_states_follow_the_machine(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    status: MachineStatus,
    power: str,
    eco: str,
    steam_boiler: str,
) -> None:
    """Eco mode needs a running machine or eco mode, the steam boiler a running machine."""
    await _setup_with_status(hass, mock_config_entry, mock_xenia_api, status)
    assert hass.states.get(POWER).state == power
    assert hass.states.get(ECO).state == eco
    assert hass.states.get(STEAM_BOILER).state == steam_boiler


@pytest.mark.parametrize(
    ("sb_status", "expected"), [(1, STATE_OFF), (2, STATE_ON), (7, STATE_OFF)]
)
async def test_steam_boiler_follows_the_boiler(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    sb_status: int,
    expected: str,
) -> None:
    """The steam boiler switch is on only while the boiler reports on."""
    await _setup_with_status(
        hass, mock_config_entry, mock_xenia_api, MachineStatus.ON, SB_STATUS=sb_status
    )
    assert hass.states.get(STEAM_BOILER).state == expected


async def test_switches_unavailable_without_machine(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    poll,
) -> None:
    """All switches are unavailable while the machine does not answer."""
    mock_xenia_api.override("get", "overview", exc=TimeoutError())
    await poll()
    for entity_id in (POWER, ECO, STEAM_BOILER):
        assert hass.states.get(entity_id).state == STATE_UNAVAILABLE


@pytest.mark.parametrize(
    ("behavior", "body"),
    [
        (None, TURN_ON_WITHOUT_STEAM),
        (PowerOnBehavior.STEAM_OFF, TURN_ON_WITHOUT_STEAM),
        (PowerOnBehavior.STEAM_ON, TURN_ON),
    ],
)
@pytest.mark.parametrize(
    ("status", "entity_id", "service"),
    [
        (MachineStatus.OFF, POWER, SERVICE_TURN_ON),
        (MachineStatus.ECO, ECO, SERVICE_TURN_OFF),
    ],
)
async def test_turning_on_honours_the_power_on_behavior(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    status: MachineStatus,
    entity_id: str,
    service: str,
    behavior: PowerOnBehavior | None,
    body: str,
) -> None:
    """Powering on and leaving eco mode start the steam boiler only if chosen."""
    await _setup_with_status(hass, mock_config_entry, mock_xenia_api, status)
    if behavior is not None:
        await hass.services.async_call(
            SELECT_DOMAIN,
            SERVICE_SELECT_OPTION,
            {ATTR_ENTITY_ID: POWER_ON_BEHAVIOR, ATTR_OPTION: behavior},
            blocking=True,
        )
    mock_xenia_api.set_overview(MA_STATUS=int(MachineStatus.ON))
    await _switch(hass, service, entity_id)
    assert mock_xenia_api.bodies("post", "machine/control") == [body]
    assert hass.states.get(POWER).state == STATE_ON


@pytest.mark.parametrize(
    ("entity_id", "service", "path", "body"),
    [
        (POWER, SERVICE_TURN_OFF, "machine/control", '{"action":"0"}'),
        (ECO, SERVICE_TURN_ON, "machine/control", '{"action":"2"}'),
        (STEAM_BOILER, SERVICE_TURN_ON, "toggle/sb", '{"TOGGLE":true,"SAVE":true}'),
        (STEAM_BOILER, SERVICE_TURN_OFF, "toggle/sb", '{"TOGGLE":false,"SAVE":true}'),
    ],
)
async def test_commands(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    entity_id: str,
    service: str,
    path: str,
    body: str,
) -> None:
    """Each switch sends its command to the machine."""
    await _switch(hass, service, entity_id)
    assert mock_xenia_api.bodies("post", path) == [body]


@pytest.mark.parametrize(
    ("entity_id", "service", "path"),
    [
        (POWER, SERVICE_TURN_ON, "machine/control"),
        (POWER, SERVICE_TURN_OFF, "machine/control"),
        (ECO, SERVICE_TURN_ON, "machine/control"),
        (ECO, SERVICE_TURN_OFF, "machine/control"),
        (STEAM_BOILER, SERVICE_TURN_ON, "toggle/sb"),
        (STEAM_BOILER, SERVICE_TURN_OFF, "toggle/sb"),
    ],
)
async def test_refused_command_raises(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    entity_id: str,
    service: str,
    path: str,
) -> None:
    """A refused command raises a translated error and still polls the machine."""
    mock_xenia_api.fail("post", path)
    polls = len(mock_xenia_api.bodies("get", "overview"))
    with pytest.raises(HomeAssistantError) as exc_info:
        await _switch(hass, service, entity_id)
    assert exc_info.value.translation_key == "write_failed"
    assert "Internal Server Error" in exc_info.value.translation_placeholders["error"]
    await hass.async_block_till_done()
    assert len(mock_xenia_api.bodies("get", "overview")) > polls
