"""Tests for sensor.py — XeniaSensor and SENSOR_TYPES definitions."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from custom_components.xenia_home.coordinator import (
    XeniaCoordinatorData,
)
from custom_components.xenia_home.sensor import SENSOR_TYPES, XeniaSensor
from custom_components.xenia_home.xenia import (
    XeniaOverviewData,
    XeniaOverviewSingleData,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_coordinator(overview_payload: dict | None = None) -> MagicMock:
    coord = MagicMock()
    coord.config_entry = MagicMock()
    coord.config_entry.data = {"host": "xenia.local"}

    overview = XeniaOverviewData.from_dict(overview_payload or {})
    overview_single = XeniaOverviewSingleData.from_dict({})
    coord.data = XeniaCoordinatorData(overview=overview, overview_single=overview_single)
    return coord


def _make_sensor(coordinator: MagicMock, description_key: str) -> XeniaSensor:
    description = next(d for d in SENSOR_TYPES if d.key == description_key)
    with patch(
        "custom_components.xenia_home.entity.XeniaEntity.__init__", return_value=None
    ):
        sensor = XeniaSensor.__new__(XeniaSensor)
        sensor.coordinator = coordinator
        sensor.hass = MagicMock()
        XeniaSensor.__init__(sensor, coordinator, description)
    return sensor


# ===========================================================================
# SENSOR_TYPES definitions
# ===========================================================================


def test_sensor_types_has_eight_entries() -> None:
    assert len(SENSOR_TYPES) == 8


def test_all_sensor_types_have_translation_key() -> None:
    for desc in SENSOR_TYPES:
        assert desc.translation_key, f"{desc.key} is missing translation_key"


def test_all_sensor_types_have_value_fn() -> None:
    for desc in SENSOR_TYPES:
        assert callable(desc.value_fn), f"{desc.key} missing value_fn"


# ===========================================================================
# XeniaSensor unique ID and attributes
# ===========================================================================


def test_sensor_unique_id_includes_host_and_key() -> None:
    coord = _make_coordinator()
    sensor = _make_sensor(coord, "brew_group_temperature")
    assert "xenia.local" in sensor._attr_unique_id
    assert "brew_group_temperature" in sensor._attr_unique_id


def test_sensor_unique_id_different_for_different_keys() -> None:
    coord = _make_coordinator()
    s1 = _make_sensor(coord, "brew_group_temperature")
    s2 = _make_sensor(coord, "pump_pressure")
    assert s1._attr_unique_id != s2._attr_unique_id


# ===========================================================================
# native_value via value_fn
# ===========================================================================


@pytest.mark.parametrize(
    "key, payload_key, payload_val, expected",
    [
        ("brew_group_temperature", "BG_SENS_TEMP_A", 93.5, 93.5),
        ("brew_boiler_temperature", "BB_SENS_TEMP_A", 130.0, 130.0),
        ("pump_pressure", "PU_SENS_PRESS", 9.1, 9.1),
        ("steam_boiler_pressure", "SB_SENS_PRESS", 1.2, 1.2),
        ("electric_current", "MA_CUR_PWR", 3.5, 3.5),
        ("total_energy", "MA_ENERGY_TOTAL_KWH", 42.5, 42.5),
        ("extractions", "MA_EXTRACTIONS", 1234, 1234),
    ],
)
def test_sensor_native_value_reads_from_overview(
    key: str, payload_key: str, payload_val: float, expected: float
) -> None:
    coord = _make_coordinator({payload_key: payload_val})
    sensor = _make_sensor(coord, key)
    assert sensor.native_value == pytest.approx(expected)


def test_sensor_operating_hours_divides_by_60() -> None:
    """Operating hours are stored in minutes and must be divided by 60."""
    coord = _make_coordinator({"MA_OPERATING_HOURS": 120})
    sensor = _make_sensor(coord, "operating_hours")
    assert sensor.native_value == pytest.approx(2.0)


def test_sensor_operating_hours_zero_input_returns_none() -> None:
    """Zero operating hours is implausible — TOTAL_INCREASING returns None."""
    coord = _make_coordinator({"MA_OPERATING_HOURS": 0})
    sensor = _make_sensor(coord, "operating_hours")
    assert sensor.native_value is None


def test_sensor_total_energy_zero_returns_none() -> None:
    """Zero energy is implausible — TOTAL_INCREASING returns None."""
    coord = _make_coordinator({"MA_ENERGY_TOTAL_KWH": 0})
    sensor = _make_sensor(coord, "total_energy")
    assert sensor.native_value is None


def test_sensor_extractions_zero_returns_none() -> None:
    """Zero extractions is implausible — TOTAL_INCREASING returns None."""
    coord = _make_coordinator({"MA_EXTRACTIONS": 0})
    sensor = _make_sensor(coord, "extractions")
    assert sensor.native_value is None


def test_sensor_native_value_defaults_to_zero_on_missing_field() -> None:
    coord = _make_coordinator({})
    sensor = _make_sensor(coord, "brew_group_temperature")
    assert sensor.native_value == pytest.approx(0.0)


# ===========================================================================
# entity_category
# ===========================================================================


def test_sensor_entity_category_returns_none_when_no_fn() -> None:
    coord = _make_coordinator()
    sensor = _make_sensor(coord, "brew_group_temperature")
    # None of the current sensor types has an entity_category_fn
    # so it should delegate to the parent which returns None by default
    assert sensor.entity_category is None


# ===========================================================================
# Device class and state class spot checks
# ===========================================================================


def test_brew_group_temperature_has_temperature_device_class() -> None:
    desc = next(d for d in SENSOR_TYPES if d.key == "brew_group_temperature")
    assert desc.device_class == SensorDeviceClass.TEMPERATURE


def test_total_energy_has_total_increasing_state_class() -> None:
    desc = next(d for d in SENSOR_TYPES if d.key == "total_energy")
    assert desc.state_class == SensorStateClass.TOTAL_INCREASING


def test_extractions_has_no_unit() -> None:
    desc = next(d for d in SENSOR_TYPES if d.key == "extractions")
    assert desc.native_unit_of_measurement is None
