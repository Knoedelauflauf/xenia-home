"""Tests for polling the machine."""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.xenia_home.const import (
    CONF_MANAGED_SCRIPT_ID,
    CONF_WEIGHT_MANAGEMENT_ENABLED,
)
from custom_components.xenia_home.xenia import MachineStatus

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
        (MachineStatus.ON, 1),
        (MachineStatus.BREWING, 1),
        (MachineStatus.DRAINING, 1),
        (MachineStatus.ECO, 5),
        (MachineStatus.OFF, 5),
        (MachineStatus.UNKNOWN, 5),
    ],
)
async def test_poll_interval_follows_the_machine(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    status: MachineStatus,
    interval: int,
) -> None:
    """The machine is polled every second while on, else every five seconds."""
    mock_xenia_api.set_overview(MA_STATUS=int(status))
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data.coordinator
    assert coordinator.update_interval == timedelta(seconds=interval)


async def test_poll_interval_changes_with_the_machine(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Turning the machine to eco slows polling down, turning it on speeds it up."""
    coordinator = init_integration.runtime_data.coordinator
    mock_xenia_api.set_overview(MA_STATUS=int(MachineStatus.ECO))
    await _pass(hass, freezer, 1)
    assert coordinator.update_interval == timedelta(seconds=5)

    mock_xenia_api.set_overview(MA_STATUS=int(MachineStatus.ON))
    await _pass(hass, freezer, 5)
    assert coordinator.update_interval == timedelta(seconds=1)


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
        {CONF_WEIGHT_MANAGEMENT_ENABLED: True, CONF_MANAGED_SCRIPT_ID: 17}
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


async def test_deleted_managed_script_is_reported(
    hass: HomeAssistant,
    weight_entry: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A managed script the machine no longer has leaves the weight unavailable."""
    mock_xenia_api.set_script(17, "", "")
    await setup_integration(hass, weight_entry)
    assert hass.states.get(WEIGHT).state == STATE_UNAVAILABLE
    assert "Managed script 17 no longer exists" in caplog.text
