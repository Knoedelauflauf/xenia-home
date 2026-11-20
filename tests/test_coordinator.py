"""Tests for polling the machine."""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.xenia_home.const import XENIA_DOMAIN

from tests import setup_integration
from tests.conftest import MockXeniaApi

TEMPERATURE = "sensor.xenia_espresso_machine_brewgroup_temperature"
SCRIPT_SELECT = "select.xenia_espresso_machine_script"
WEIGHT = "number.xenia_espresso_machine_script_weight_target"


async def _pass(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float
) -> None:
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


@pytest.mark.parametrize(
    ("status", "interval"),
    [
        (1, 1),
        (3, 1),
        (4, 1),
        (2, 5),
        (0, 5),
        (42, 5),
    ],
)
async def test_poll_interval_follows_the_machine(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    freezer: FrozenDateTimeFactory,
    status: int,
    interval: int,
) -> None:
    """The machine is polled every second while on, else every five seconds."""
    mock_xenia_api.set_overview(MA_STATUS=int(status))
    await setup_integration(hass, mock_config_entry)
    polls = len(mock_xenia_api.bodies("get", "overview"))
    for _ in range(10):
        await _pass(hass, freezer, 1)
    assert len(mock_xenia_api.bodies("get", "overview")) == polls + 10 // interval


async def test_poll_interval_changes_with_the_machine(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Turning the machine to eco slows polling down, turning it on speeds it up."""
    mock_xenia_api.set_overview(MA_STATUS=2)
    await _pass(hass, freezer, 1)
    polls = len(mock_xenia_api.bodies("get", "overview"))
    for _ in range(10):
        await _pass(hass, freezer, 1)
    assert len(mock_xenia_api.bodies("get", "overview")) == polls + 2

    mock_xenia_api.set_overview(MA_STATUS=1)
    for _ in range(5):
        await _pass(hass, freezer, 1)
    polls = len(mock_xenia_api.bodies("get", "overview"))
    for _ in range(3):
        await _pass(hass, freezer, 1)
    assert len(mock_xenia_api.bodies("get", "overview")) == polls + 3


async def test_polling_can_be_left_to_automations(
    hass: HomeAssistant,
    mock_xenia_api: MockXeniaApi,
    freezer: FrozenDateTimeFactory,
) -> None:
    """With polling disabled the machine is only read on homeassistant.update_entity."""
    await async_setup_component(hass, "homeassistant", {})
    entry = MockConfigEntry(
        domain="xenia_home",
        title="xenia.local",
        unique_id="aa:bb:cc:dd:ee:ff",
        minor_version=2,
        data={"host": "xenia.local"},
        pref_disable_polling=True,
    )
    await setup_integration(hass, entry)
    polls = len(mock_xenia_api.bodies("get", "overview"))
    for _ in range(10):
        await _pass(hass, freezer, 1)
    assert len(mock_xenia_api.bodies("get", "overview")) == polls

    mock_xenia_api.set_overview(BG_SENS_TEMP_A=94.5)
    await hass.services.async_call(
        "homeassistant",
        "update_entity",
        {ATTR_ENTITY_ID: TEMPERATURE},
        blocking=True,
    )
    assert len(mock_xenia_api.bodies("get", "overview")) == polls + 1
    assert hass.states.get(TEMPERATURE).state == "94.5"


@pytest.mark.parametrize("path", ["overview", "overview_single"])
async def test_entities_are_unavailable_while_machine_does_not_answer(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    freezer: FrozenDateTimeFactory,
    path: str,
) -> None:
    """A failed poll makes the entities unavailable until the next good one."""
    mock_xenia_api.override("get", path, exc=TimeoutError())
    await _pass(hass, freezer, 1)
    assert hass.states.get(TEMPERATURE).state == STATE_UNAVAILABLE

    mock_xenia_api.restore("get", path)
    mock_xenia_api.set_overview(BG_SENS_TEMP_A=91.0)
    await _pass(hass, freezer, 1)
    assert hass.states.get(TEMPERATURE).state == "91.0"


@pytest.mark.parametrize(
    "path", ["overview", "overview_single", "machine", "scripts/list", "switches"]
)
async def test_setup_retries_while_machine_unreachable(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    path: str,
) -> None:
    """Setup is retried later when the machine does not answer."""
    mock_xenia_api.override("get", path, exc=OSError("unreachable"))
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_scripts_include_the_builtin_ones(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
) -> None:
    """The scripts are the built-in ones plus the machine's; the machine's win."""
    mock_xenia_api.set_scripts({1: "Custom", 10: "MyShot"})
    await setup_integration(hass, mock_config_entry)
    assert hass.states.get(SCRIPT_SELECT).attributes["options"] == [
        "None",
        "Custom",
        "Espresso endless",
        "MyShot",
    ]


async def test_script_changes_arrive_within_an_hour(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Scripts are polled hourly, without a reload."""
    mock_xenia_api.set_scripts({10: "MyShot renamed"})
    await _pass(hass, freezer, 3601)
    options = hass.states.get(SCRIPT_SELECT).attributes["options"]
    assert "MyShot renamed" in options
    assert "MyShot" not in options


async def test_failed_config_poll_is_retried_within_a_minute(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    freezer: FrozenDateTimeFactory,
) -> None:
    """After a failed hourly poll the scripts are read again a minute later."""
    mock_xenia_api.fail("get", "switches")
    mock_xenia_api.set_scripts({10: "MyShot renamed"})
    await _pass(hass, freezer, 3601)
    mock_xenia_api.restore("get", "switches")
    await _pass(hass, freezer, 61)
    assert "MyShot renamed" in hass.states.get(SCRIPT_SELECT).attributes["options"]


@pytest.fixture
def weight_entry(mock_config_entry_factory_with_options) -> MockConfigEntry:
    """Return an entry that manages the weight of script 17."""
    return mock_config_entry_factory_with_options(
        {"weight_management_enabled": True, "managed_script_id": 17}
    )


async def test_managed_script_is_read(
    hass: HomeAssistant, weight_entry: MockConfigEntry, mock_xenia_api: MockXeniaApi
) -> None:
    """The weight target comes from the managed script."""
    mock_xenia_api.set_script(17, "1;13;27 45;7;", "My Shot")
    await setup_integration(hass, weight_entry)
    assert hass.states.get(WEIGHT).state == "45.0"


async def test_unreadable_managed_script_only_affects_the_weight(
    hass: HomeAssistant,
    weight_entry: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A failed script read leaves only the weight target unavailable, for a minute."""
    mock_xenia_api.fail("post", "scripts/read")
    await setup_integration(hass, weight_entry)
    assert weight_entry.state is ConfigEntryState.LOADED
    assert hass.states.get(WEIGHT).state == STATE_UNAVAILABLE
    assert hass.states.get(TEMPERATURE).state != STATE_UNAVAILABLE

    mock_xenia_api.restore("post", "scripts/read")
    mock_xenia_api.set_script(17, "1;13;27 45;7;", "My Shot")
    await _pass(hass, freezer, 61)
    assert hass.states.get(WEIGHT).state == "45.0"


async def test_deleted_managed_script_raises_a_repair_issue(
    hass: HomeAssistant,
    weight_entry: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    issue_registry: ir.IssueRegistry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A managed script the machine no longer has is a repair issue until it is back."""
    issue_id = f"managed_script_missing_{weight_entry.entry_id}"
    mock_xenia_api.set_script(17, "", "")
    await setup_integration(hass, weight_entry)
    assert hass.states.get(WEIGHT).state == STATE_UNAVAILABLE
    issue = issue_registry.async_get_issue(XENIA_DOMAIN, issue_id)
    assert issue is not None
    assert issue.translation_placeholders == {
        "script_id": "17",
        "title": weight_entry.title,
    }

    mock_xenia_api.set_script(17, "1;13;27 45;7;", "My Shot")
    await _pass(hass, freezer, 3601)
    assert hass.states.get(WEIGHT).state == "45.0"
    assert issue_registry.async_get_issue(XENIA_DOMAIN, issue_id) is None


async def test_repair_issue_ends_with_weight_management(
    hass: HomeAssistant,
    weight_entry: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    issue_registry: ir.IssueRegistry,
) -> None:
    """Turning weight management off, or removing the entry, clears the issue."""
    issue_id = f"managed_script_missing_{weight_entry.entry_id}"
    mock_xenia_api.set_script(17, "", "")
    await setup_integration(hass, weight_entry)
    assert issue_registry.async_get_issue(XENIA_DOMAIN, issue_id) is not None

    hass.config_entries.async_update_entry(
        weight_entry, options={"weight_management_enabled": False}
    )
    await hass.config_entries.async_reload(weight_entry.entry_id)
    await hass.async_block_till_done()
    assert issue_registry.async_get_issue(XENIA_DOMAIN, issue_id) is None

    hass.config_entries.async_update_entry(
        weight_entry,
        options={"weight_management_enabled": True, "managed_script_id": 17},
    )
    await hass.config_entries.async_reload(weight_entry.entry_id)
    await hass.async_block_till_done()
    assert issue_registry.async_get_issue(XENIA_DOMAIN, issue_id) is not None
    await hass.config_entries.async_remove(weight_entry.entry_id)
    assert issue_registry.async_get_issue(XENIA_DOMAIN, issue_id) is None
