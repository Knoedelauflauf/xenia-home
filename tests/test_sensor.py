"""Tests for the sensors."""

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from syrupy.assertion import SnapshotAssertion

from tests import setup_integration
from tests.conftest import MockXeniaApi

STATUS = "sensor.xenia_espresso_machine_status"
SHOT_START = "sensor.xenia_espresso_machine_shot_start_time"
SCALE_FLOW = "sensor.xenia_espresso_machine_scale_flow_rate"


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_sensor_entities_snapshot(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
) -> None:
    """The sensors match the snapshot."""
    entity_ids = sorted(
        e.entity_id
        for e in er.async_entries_for_config_entry(
            entity_registry, init_integration.entry_id
        )
        if e.domain == SENSOR_DOMAIN
    )
    assert len(entity_ids) == 11
    for entity_id in entity_ids:
        assert hass.states.get(entity_id) == snapshot(name=f"{entity_id}-state")
        assert entity_registry.async_get(entity_id) == snapshot(
            name=f"{entity_id}-registry"
        )


@pytest.mark.parametrize(("minutes", "hours"), [(120, "2.0"), (90, "1.5")])
async def test_operating_hours(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    minutes: int,
    hours: str,
) -> None:
    """The machine counts operating minutes; the sensor shows hours."""
    mock_xenia_api.set_overview(MA_OPERATING_HOURS=minutes)
    await setup_integration(hass, mock_config_entry)
    assert (
        hass.states.get("sensor.xenia_espresso_machine_operating_hours").state == hours
    )


@pytest.mark.parametrize(
    ("sensor", "field"),
    [
        ("operating_hours", "MA_OPERATING_HOURS"),
        ("total_energy", "MA_ENERGY_TOTAL_KWH"),
        ("extractions", "MA_EXTRACTIONS"),
    ],
)
async def test_zero_counter_is_unknown(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    sensor: str,
    field: str,
) -> None:
    """A counter reading zero is a failed read, not a reset; it shows as unknown."""
    mock_xenia_api.set_overview(**{field: 0})
    await setup_integration(hass, mock_config_entry)
    assert (
        hass.states.get(f"sensor.xenia_espresso_machine_{sensor}").state
        == STATE_UNKNOWN
    )


async def test_missing_value_is_unknown(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
) -> None:
    """A value the machine leaves out shows as unknown; the sensor stays available."""
    mock_xenia_api.set_overview(BG_SENS_TEMP_A=None, MA_OPERATING_HOURS=None)
    await setup_integration(hass, mock_config_entry)
    for sensor in ("brewgroup_temperature", "operating_hours"):
        state = hass.states.get(f"sensor.xenia_espresso_machine_{sensor}")
        assert state.state == STATE_UNKNOWN


async def test_scale_flow_rate_on_new_firmware(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
) -> None:
    """Firmware with a scale adds the scale flow rate sensor."""
    await setup_integration(hass, mock_config_entry)
    state = hass.states.get(SCALE_FLOW)
    assert state.state == "1.27"
    assert state.attributes["unit_of_measurement"] == "g/s"


async def test_no_scale_flow_rate_on_old_firmware(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
) -> None:
    """Firmware without a scale has no scale flow rate sensor."""
    mock_xenia_api.use_old_firmware()
    await setup_integration(hass, mock_config_entry)
    assert hass.states.get(SCALE_FLOW) is None


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (0, "off"),
        (1, "on"),
        (2, "eco"),
        (3, "brewing"),
        (4, "draining"),
        (42, STATE_UNKNOWN),
    ],
)
async def test_status(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    status: int,
    expected: str,
) -> None:
    """The status sensor names the machine state; an unknown code is unknown."""
    mock_xenia_api.set_overview(MA_STATUS=status)
    await setup_integration(hass, mock_config_entry)
    assert hass.states.get(STATUS).state == expected


async def test_shot_running_at_load_is_timed_from_the_load(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A shot that is already brewing when the integration loads starts at the load."""
    mock_xenia_api.set_overview(MA_STATUS=3)
    await setup_integration(hass, mock_config_entry)
    started = dt_util.parse_datetime(hass.states.get(SHOT_START).state)
    assert started == dt_util.utcnow().replace(microsecond=0)


async def test_shot_start_time_follows_the_shot(
    hass: HomeAssistant, init_integration: MockConfigEntry, poll
) -> None:
    """The shot start time is set while brewing and cleared after."""
    assert hass.states.get(SHOT_START).state == STATE_UNKNOWN

    await poll(MA_STATUS=3)
    started = hass.states.get(SHOT_START).state
    assert dt_util.parse_datetime(started) == dt_util.utcnow().replace(microsecond=0)

    await poll(MA_STATUS=3)
    assert hass.states.get(SHOT_START).state == started

    await poll(MA_STATUS=1)
    assert hass.states.get(SHOT_START).state == STATE_UNKNOWN
