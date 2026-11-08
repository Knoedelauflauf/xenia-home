"""Tests for sensor.py — sensor entities."""

from unittest.mock import AsyncMock, patch

from homeassistant.util import dt as dt_util
import pytest

from custom_components.xenia_home.xenia import MachineStatus, XeniaOverviewData
from tests.fixtures.api_responses import OVERVIEW_NEW_FW_FIELDS, OVERVIEW_PAYLOAD


async def test_sensor_entities_snapshot(
    hass, init_integration, snapshot, entity_registry
):
    entity_ids = sorted(
        e.entity_id
        for e in entity_registry.entities.values()
        if e.platform == "xenia_home" and e.domain == "sensor"
    )
    assert len(entity_ids) == 10, f"expected 10 sensors, got {entity_ids}"
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        registry_entry = entity_registry.async_get(entity_id)
        assert state == snapshot(name=f"{entity_id}-state")
        assert registry_entry == snapshot(name=f"{entity_id}-registry")


# ===========================================================================
# value_fn behaviors — only the non-trivial ones get explicit tests.
# Direct passthrough sensors (brew_group_temperature, pump_pressure, ...)
# are fully covered by the snapshot above.
# ===========================================================================


@pytest.mark.parametrize(
    ("minutes", "expected_hours"),
    [
        (120, 2.0),
        (60, 1.0),
        (90, 1.5),
    ],
)
async def test_operating_hours_divides_minutes_by_60(
    hass,
    enable_custom_integrations,
    mock_xenia_api,
    mock_config_entry,
    minutes,
    expected_hours,
):
    mock_xenia_api.set_overview(MA_OPERATING_HOURS=minutes)
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get("sensor.xenia_espresso_machine_operating_hours")
    assert state is not None
    assert float(state.state) == pytest.approx(expected_hours)


@pytest.mark.parametrize(
    ("sensor_key", "payload_key"),
    [
        ("operating_hours", "MA_OPERATING_HOURS"),
        ("total_energy", "MA_ENERGY_TOTAL_KWH"),
        ("extractions", "MA_EXTRACTIONS"),
    ],
)
async def test_total_increasing_sensor_zero_value_becomes_unknown(
    hass,
    enable_custom_integrations,
    mock_xenia_api,
    mock_config_entry,
    sensor_key,
    payload_key,
):
    """Zero on a TOTAL_INCREASING counter is implausible and reported as unknown."""
    mock_xenia_api.set_overview(**{payload_key: 0})
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get(f"sensor.xenia_espresso_machine_{sensor_key}")
    assert state is not None
    assert state.state in ("unknown", "unavailable")


async def test_passthrough_sensor_reads_from_overview(
    hass, enable_custom_integrations, mock_xenia_api, mock_config_entry
):
    mock_xenia_api.set_overview(BG_SENS_TEMP_A=88.7)
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get("sensor.xenia_espresso_machine_brewgroup_temperature")
    assert float(state.state) == pytest.approx(88.7)


async def test_scale_flow_rate_sensor_created_on_new_firmware(
    hass, enable_custom_integrations, mock_xenia_api, mock_config_entry
):
    mock_xenia_api.set_overview(**OVERVIEW_NEW_FW_FIELDS)
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get("sensor.xenia_espresso_machine_scale_flow_rate")
    assert state is not None
    assert float(state.state) == pytest.approx(1.27)
    assert state.attributes["unit_of_measurement"] == "g/s"


async def test_scale_flow_rate_sensor_absent_on_old_firmware(hass, init_integration):
    assert hass.states.get("sensor.xenia_espresso_machine_scale_flow_rate") is None


async def test_status_and_shot_start_time_while_brewing(
    hass, enable_custom_integrations, mock_xenia_api, mock_config_entry
):
    mock_xenia_api.set_overview(MA_STATUS=3)
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.xenia_espresso_machine_status").state == "brewing"
    start = hass.states.get("sensor.xenia_espresso_machine_shot_start_time").state
    assert dt_util.parse_datetime(start) is not None


async def test_status_sensor_unknown_for_unrecognised_status(
    hass, enable_custom_integrations, mock_xenia_api, mock_config_entry
):
    mock_xenia_api.set_overview(MA_STATUS=42)
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.xenia_espresso_machine_status").state == "unknown"


async def test_shot_start_time_follows_the_shot(hass, init_integration):
    coordinator = init_integration.runtime_data.coordinator

    async def poll(status: MachineStatus) -> str:
        overview = XeniaOverviewData.from_dict(
            {**OVERVIEW_PAYLOAD, "MA_STATUS": int(status)}
        )
        with patch.object(
            coordinator.xenia, "get_overview", AsyncMock(return_value=overview)
        ):
            await coordinator.async_refresh()
        await hass.async_block_till_done()
        return hass.states.get("sensor.xenia_espresso_machine_shot_start_time").state

    started = await poll(MachineStatus.BREWING)
    assert dt_util.parse_datetime(started) is not None
    assert await poll(MachineStatus.BREWING) == started
    assert await poll(MachineStatus.ON) == "unknown"
