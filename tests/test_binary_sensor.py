"""Tests for binary_sensor.py — XeniaWaterTankSensor."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from custom_components.xenia_home.binary_sensor import XeniaWaterTankSensor
from custom_components.xenia_home.coordinator import XeniaCoordinatorData
from custom_components.xenia_home.xenia import (
    XeniaOverviewData,
    XeniaOverviewSingleData,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_coordinator(water_tank_level: int = 1) -> MagicMock:
    coord = MagicMock()
    coord.config_entry = MagicMock()
    coord.config_entry.data = {"host": "xenia.local"}

    overview = XeniaOverviewData.from_dict({})
    overview_single = XeniaOverviewSingleData.from_dict(
        {"PU_SENS_WATER_TANK_LEVEL": water_tank_level}
    )
    coord.data = XeniaCoordinatorData(overview=overview, overview_single=overview_single)
    return coord


def _make_sensor(coordinator: MagicMock) -> XeniaWaterTankSensor:
    with patch(
        "custom_components.xenia_home.entity.XeniaEntity.__init__", return_value=None
    ):
        sensor = XeniaWaterTankSensor.__new__(XeniaWaterTankSensor)
        sensor.coordinator = coordinator
        sensor.hass = MagicMock()
        XeniaWaterTankSensor.__init__(sensor, coordinator)
    return sensor


# ===========================================================================
# Attributes
# ===========================================================================


def test_water_tank_sensor_unique_id_includes_host() -> None:
    coord = _make_coordinator()
    sensor = _make_sensor(coord)
    assert "xenia.local" in sensor._attr_unique_id


def test_water_tank_sensor_unique_id_contains_water_tank_empty() -> None:
    coord = _make_coordinator()
    sensor = _make_sensor(coord)
    assert "water_tank_empty" in sensor._attr_unique_id


def test_water_tank_sensor_translation_key() -> None:
    coord = _make_coordinator()
    sensor = _make_sensor(coord)
    assert sensor._attr_translation_key == "water_tank_empty"


def test_water_tank_sensor_device_class_is_problem() -> None:
    coord = _make_coordinator()
    sensor = _make_sensor(coord)
    assert sensor._attr_device_class == BinarySensorDeviceClass.PROBLEM


# ===========================================================================
# is_on — the logic that matters
# ===========================================================================


@pytest.mark.parametrize(
    "level, expected_is_on",
    [
        (1, False),   # water present — no problem
        (2, True),    # tank empty — problem active
        (0, False),   # unexpected value — should not be treated as empty
        (3, False),   # unexpected value — should not be treated as empty
        (99, False),  # completely unknown level
    ],
)
def test_water_tank_sensor_is_on_for_level(level: int, expected_is_on: bool) -> None:
    coord = _make_coordinator(water_tank_level=level)
    sensor = _make_sensor(coord)
    assert sensor.is_on == expected_is_on


def test_water_tank_sensor_is_on_true_when_level_two() -> None:
    coord = _make_coordinator(water_tank_level=2)
    sensor = _make_sensor(coord)
    assert sensor.is_on is True


def test_water_tank_sensor_is_on_false_when_level_one() -> None:
    coord = _make_coordinator(water_tank_level=1)
    sensor = _make_sensor(coord)
    assert sensor.is_on is False
