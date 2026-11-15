"""Tests for the power on behavior, script and switch selects."""

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.select import (
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_OPTION, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache,
)
from syrupy.assertion import SnapshotAssertion

from tests import pass_seconds, setup_integration
from tests.conftest import MockXeniaApi

pytestmark = pytest.mark.usefixtures("entity_registry_enabled_by_default")

POWER_ON_BEHAVIOR = "select.xenia_espresso_machine_power_on_behavior"
SCRIPT = "select.xenia_espresso_machine_script"
SWITCH_LEFT_SHORT = "select.xenia_espresso_machine_left_switch_left_short"
SWITCH_RIGHT_LONG = "select.xenia_espresso_machine_right_switch_right_long"


async def _select(hass: HomeAssistant, entity_id: str, option: str) -> None:
    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: entity_id, ATTR_OPTION: option},
        blocking=True,
    )


async def test_select_entities_snapshot(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
) -> None:
    """The selects match the snapshot."""
    entity_ids = sorted(
        e.entity_id
        for e in er.async_entries_for_config_entry(
            entity_registry, init_integration.entry_id
        )
        if e.domain == SELECT_DOMAIN
    )
    assert len(entity_ids) == 8
    for entity_id in entity_ids:
        assert hass.states.get(entity_id) == snapshot(name=f"{entity_id}-state")
        assert entity_registry.async_get(entity_id) == snapshot(
            name=f"{entity_id}-registry"
        )


async def test_power_on_behavior_defaults_to_steam_off(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Without a stored choice the steam boiler stays off on power on."""
    assert hass.states.get(POWER_ON_BEHAVIOR).state == "steam_off"


async def test_power_on_behavior_is_kept_across_reloads(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The choice is a local preference that survives a reload."""
    await _select(hass, POWER_ON_BEHAVIOR, "steam_on")
    assert hass.states.get(POWER_ON_BEHAVIOR).state == "steam_on"

    await hass.config_entries.async_reload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(POWER_ON_BEHAVIOR).state == "steam_on"


@pytest.mark.parametrize(
    ("restored", "expected"),
    [
        ("steam_on", "steam_on"),
        (STATE_UNAVAILABLE, "steam_off"),
    ],
)
async def test_power_on_behavior_is_restored_after_restart(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    restored: str,
    expected: str,
) -> None:
    """The choice is restored after a restart; an unusable stored state is ignored."""
    mock_restore_cache(hass, (State(POWER_ON_BEHAVIOR, restored),))
    await setup_integration(hass, mock_config_entry)
    assert hass.states.get(POWER_ON_BEHAVIOR).state == expected


async def test_power_on_behavior_stays_available_without_machine(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    poll,
) -> None:
    """An unreachable machine does not make the choice unavailable.

    An unavailable state would be stored and restored after a restart.
    """
    mock_xenia_api.override("get", "overview", exc=TimeoutError())
    await poll()
    assert hass.states.get(SCRIPT).state == STATE_UNAVAILABLE
    assert hass.states.get(POWER_ON_BEHAVIOR).state == "steam_off"


async def test_power_on_behavior_rejects_unknown_options(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Only the listed options can be selected."""
    with pytest.raises(ServiceValidationError):
        await _select(hass, POWER_ON_BEHAVIOR, "garbage")


async def test_script_select(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The script select offers all scripts and shows the selected one."""
    state = hass.states.get(SCRIPT)
    assert state.attributes["options"] == [
        "None",
        "Espresso",
        "Espresso endless",
        "MyShot",
        "Lungo",
    ]
    assert state.state == "unknown"

    await _select(hass, SCRIPT, "Lungo")
    assert hass.states.get(SCRIPT).state == "Lungo"


async def test_switch_select_shows_the_assigned_script(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """A switch shows its script; a switch without assignment shows "None"."""
    assert hass.states.get(SWITCH_LEFT_SHORT).state == "Espresso"
    assert hass.states.get(SWITCH_RIGHT_LONG).state == "None"


async def test_switch_select_assigns_a_script(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Selecting a script assigns it on the machine and reads it back a second later."""
    mock_xenia_api.set_switches({"SWITCH_SET_LEFT_LEFT_0": 10})
    await _select(hass, SWITCH_LEFT_SHORT, "MyShot")
    assert mock_xenia_api.bodies("post", "switches") == [
        '{"SWITCH_SET_LEFT_LEFT_0":"10"}'
    ]
    await pass_seconds(hass, freezer, 1)
    assert hass.states.get(SWITCH_LEFT_SHORT).state == "MyShot"


async def test_refused_switch_assignment_raises(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_xenia_api: MockXeniaApi
) -> None:
    """A refused assignment raises a translated error."""
    mock_xenia_api.fail("post", "switches")
    with pytest.raises(HomeAssistantError) as exc_info:
        await _select(hass, SWITCH_LEFT_SHORT, "MyShot")
    assert exc_info.value.translation_key == "write_failed"
