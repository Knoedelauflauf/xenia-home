"""Tests for polling the machine."""

import asyncio
from itertools import pairwise
import logging

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_ENTITY_ID,
    EVENT_STATE_CHANGED,
    STATE_OFF,
    STATE_UNAVAILABLE,
)
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xenia_home.const import XENIA_DOMAIN

from tests import pass_seconds, run_for, setup_integration
from tests.conftest import MockXeniaApi

TEMPERATURE = "sensor.xenia_espresso_machine_brewgroup_temperature"
WATER_TANK = "binary_sensor.xenia_espresso_machine_water_tank_empty"
BREW_GROUP_SETPOINT = "number.xenia_espresso_machine_brewgroup_set_temperature"
STEAM_BOILER = "switch.xenia_espresso_machine_steam_boiler_power"
SCRIPT_SELECT = "select.xenia_espresso_machine_script"
WEIGHT = "number.xenia_espresso_machine_script_weight_target"


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
        await pass_seconds(hass, freezer, 1)
    assert len(mock_xenia_api.bodies("get", "overview")) == polls + 10 // interval


async def test_poll_interval_changes_with_the_machine(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Turning the machine to eco slows polling down, turning it on speeds it up."""
    mock_xenia_api.set_overview(MA_STATUS=2)
    await pass_seconds(hass, freezer, 1)
    polls = len(mock_xenia_api.bodies("get", "overview"))
    for _ in range(10):
        await pass_seconds(hass, freezer, 1)
    assert len(mock_xenia_api.bodies("get", "overview")) == polls + 2

    mock_xenia_api.set_overview(MA_STATUS=1)
    for _ in range(5):
        await pass_seconds(hass, freezer, 1)
    polls = len(mock_xenia_api.bodies("get", "overview"))
    for _ in range(3):
        await pass_seconds(hass, freezer, 1)
    assert len(mock_xenia_api.bodies("get", "overview")) == polls + 3


async def test_polling_can_be_left_to_automations(
    hass: HomeAssistant,
    mock_xenia_api: MockXeniaApi,
    freezer: FrozenDateTimeFactory,
) -> None:
    """With polling disabled the machine is only read on homeassistant.update_entity, each part through its own entities."""
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
    single_polls = len(mock_xenia_api.bodies("get", "overview_single"))
    for _ in range(10):
        await pass_seconds(hass, freezer, 1)
    assert len(mock_xenia_api.bodies("get", "overview")) == polls
    assert len(mock_xenia_api.bodies("get", "overview_single")) == single_polls

    mock_xenia_api.set_overview(BG_SENS_TEMP_A=94.5)
    mock_xenia_api.set_overview_single(PU_SENS_WATER_TANK_LEVEL=2)
    await hass.services.async_call(
        "homeassistant",
        "update_entity",
        {ATTR_ENTITY_ID: TEMPERATURE},
        blocking=True,
    )
    assert len(mock_xenia_api.bodies("get", "overview")) == polls + 1
    assert hass.states.get(TEMPERATURE).state == "94.5"
    assert len(mock_xenia_api.bodies("get", "overview_single")) == single_polls
    assert hass.states.get(WATER_TANK).state == "off"

    await hass.services.async_call(
        "homeassistant",
        "update_entity",
        {ATTR_ENTITY_ID: WATER_TANK},
        blocking=True,
    )
    assert len(mock_xenia_api.bodies("get", "overview_single")) == single_polls + 1
    assert hass.states.get(WATER_TANK).state == "on"


@pytest.mark.parametrize("status", [1, 2])
async def test_setpoints_and_water_tank_are_polled_every_ten_seconds(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_config_entry: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    status: int,
) -> None:
    """overview_single is read every ten seconds, however long overview takes to answer."""
    mock_xenia_api.set_overview(MA_STATUS=status)
    mock_xenia_api.answer_slowly(freezer, "overview_single", 0.2)
    await setup_integration(hass, mock_config_entry)
    for answer_time in (0.02, 0.2, 0.1, 0.2, 0.02, 0.2, 0.1, 0.2, 0.02):
        mock_xenia_api.answer_slowly(freezer, "overview", answer_time)
        await run_for(hass, freezer, 5)

    times = mock_xenia_api.times("get", "overview_single")
    assert len(times) == 5
    # The first poll after setup is scheduled when the entities subscribe.
    assert [b - a for a, b in pairwise(times[1:])] == pytest.approx(
        [10] * (len(times) - 2), abs=0.25
    )


async def _open_weight_options(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"weight_management_enabled": True}
    )
    assert result["step_id"] == "select_script"


async def test_requests_to_the_machine_never_overlap(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
) -> None:
    """The machine answers one request at a time, so polls, commands and options wait for each other."""
    await async_setup_component(hass, "homeassistant", {})
    for path in (
        "overview",
        "overview_single",
        "machine",
        "scripts/list",
        "inc_dec",
        "toggle/sb",
    ):
        mock_xenia_api.answer_slowly(freezer, path, 0.1)
    for _ in range(3):
        await pass_seconds(hass, freezer, 10)
    await pass_seconds(hass, freezer, 3600)
    await asyncio.gather(
        hass.services.async_call(
            "number",
            "set_value",
            {ATTR_ENTITY_ID: BREW_GROUP_SETPOINT, "value": 92.0},
            blocking=True,
        ),
        hass.services.async_call(
            "switch", "turn_on", {ATTR_ENTITY_ID: STEAM_BOILER}, blocking=True
        ),
        hass.services.async_call(
            "homeassistant",
            "update_entity",
            {ATTR_ENTITY_ID: [TEMPERATURE, WATER_TANK]},
            blocking=True,
        ),
        _open_weight_options(hass, init_integration),
    )
    await pass_seconds(hass, freezer, 1)

    assert mock_xenia_api.bodies("post", "inc_dec")
    assert mock_xenia_api.bodies("post", "toggle/sb")
    assert mock_xenia_api.max_in_flight == 1


async def test_entities_are_unavailable_while_machine_does_not_answer(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A failed poll makes the entities unavailable until the next good one."""
    mock_xenia_api.override("get", "overview", exc=TimeoutError())
    await pass_seconds(hass, freezer, 1)
    assert hass.states.get(TEMPERATURE).state == STATE_UNAVAILABLE

    mock_xenia_api.restore("get", "overview")
    mock_xenia_api.set_overview(BG_SENS_TEMP_A=91.0)
    await pass_seconds(hass, freezer, 1)
    assert hass.states.get(TEMPERATURE).state == "91.0"


async def test_offline_machine_is_logged_once_per_coordinator(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A machine that stops answering is logged once for the live values and once for the setpoints, and the same when it is back."""
    caplog.set_level(logging.INFO, logger="custom_components.xenia_home")
    for path in ("overview", "overview_single"):
        mock_xenia_api.override("get", path, exc=TimeoutError())
    for _ in range(25):
        await pass_seconds(hass, freezer, 1)
    for path in ("overview", "overview_single"):
        mock_xenia_api.restore("get", path)
    for _ in range(25):
        await pass_seconds(hass, freezer, 1)

    records = [r for r in caplog.records if r.name.startswith("custom_components")]
    assert len([r for r in records if r.levelno >= logging.WARNING]) == 2
    assert len([r for r in records if "recovered" in r.getMessage()]) == 2


async def test_setpoints_and_water_tank_are_fresh_after_an_outage(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
) -> None:
    """After an outage they go from unavailable straight to fresh values."""
    mock_xenia_api.set_overview_single(PU_SENS_WATER_TANK_LEVEL=2, BG_SET_TEMP=92.0)
    await pass_seconds(hass, freezer, 10)
    states: dict[str, list[str]] = {WATER_TANK: [], BREW_GROUP_SETPOINT: []}

    @callback
    def record(event: Event[EventStateChangedData]) -> None:
        if (new_state := event.data["new_state"]) and new_state.entity_id in states:
            states[new_state.entity_id].append(new_state.state)

    hass.bus.async_listen(EVENT_STATE_CHANGED, record)
    mock_xenia_api.answer_slowly(freezer, "overview_single", 0.3)
    for path in ("overview", "overview_single"):
        mock_xenia_api.override("get", path, exc=TimeoutError())
    for _ in range(12):
        await pass_seconds(hass, freezer, 1)
    for path in ("overview", "overview_single"):
        mock_xenia_api.restore("get", path)
    mock_xenia_api.set_overview_single()
    for _ in range(10):
        await pass_seconds(hass, freezer, 1)
    assert states == {
        WATER_TANK: [STATE_UNAVAILABLE, STATE_OFF],
        BREW_GROUP_SETPOINT: [STATE_UNAVAILABLE, "93.5"],
    }


@pytest.mark.parametrize(
    "paths", [("overview_single",), ("overview", "overview_single")]
)
async def test_failing_overview_single_is_requested_every_ten_seconds(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    paths: tuple[str, ...],
) -> None:
    """A failing overview_single is retried at most once per ten seconds."""
    polls = len(mock_xenia_api.bodies("get", "overview_single"))
    for path in paths:
        mock_xenia_api.fail("get", path)
    for _ in range(30):
        await pass_seconds(hass, freezer, 1)
    assert len(mock_xenia_api.bodies("get", "overview_single")) - polls in (2, 3)


async def test_failed_overview_single_only_affects_its_entities(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
) -> None:
    """Without overview_single the water tank and setpoints are unavailable, nothing else."""
    mock_xenia_api.override("get", "overview_single", exc=TimeoutError())
    await pass_seconds(hass, freezer, 11)
    assert hass.states.get(WATER_TANK).state == STATE_UNAVAILABLE
    assert hass.states.get(BREW_GROUP_SETPOINT).state == STATE_UNAVAILABLE
    assert hass.states.get(TEMPERATURE).state != STATE_UNAVAILABLE

    mock_xenia_api.restore("get", "overview_single")
    await pass_seconds(hass, freezer, 11)
    assert hass.states.get(WATER_TANK).state == STATE_OFF
    assert hass.states.get(BREW_GROUP_SETPOINT).state != STATE_UNAVAILABLE


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
    await pass_seconds(hass, freezer, 3601)
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
    await pass_seconds(hass, freezer, 3601)
    mock_xenia_api.restore("get", "switches")
    await pass_seconds(hass, freezer, 61)
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
    await pass_seconds(hass, freezer, 61)
    assert hass.states.get(WEIGHT).state == "45.0"


async def test_unreadable_managed_script_is_logged_once(
    hass: HomeAssistant,
    weight_entry: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failing script read is logged once, however often it is retried, and once when it is back."""
    mock_xenia_api.fail("post", "scripts/read")
    await setup_integration(hass, weight_entry)
    await pass_seconds(hass, freezer, 61)
    await pass_seconds(hass, freezer, 61)
    assert caplog.text.count("Failed to read managed script 17") == 1

    mock_xenia_api.restore("post", "scripts/read")
    mock_xenia_api.set_script(17, "1;13;27 45;7;", "My Shot")
    await pass_seconds(hass, freezer, 61)
    await pass_seconds(hass, freezer, 3601)
    assert caplog.text.count("Managed script 17 can be read again") == 1


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
    await pass_seconds(hass, freezer, 3601)
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
