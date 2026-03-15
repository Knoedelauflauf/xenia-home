"""Shared pytest fixtures for the xenia_home integration tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.xenia_home.coordinator import (
    XeniaConfigData,
    XeniaCoordinatorData,
)
from custom_components.xenia_home.xenia import (
    XeniaMachineData,
    XeniaOverviewData,
    XeniaOverviewSingleData,
)

# ---------------------------------------------------------------------------
# Raw API response fixtures
# ---------------------------------------------------------------------------

OVERVIEW_PAYLOAD: dict[str, Any] = {
    "MA_EXTRACTIONS": 1234,
    "MA_OPERATING_HOURS": 720,
    "MA_STATUS": 1,
    "MA_CLOCK": 0,
    "MA_CUR_PWR": 3.2,
    "MA_MAX_PWR": 16,
    "MA_ENERGY_TOTAL_KWH": 42.5,
    "BG_SENS_TEMP_A": 93.0,
    "BG_LEVEL_PW_CONTROL": 50,
    "PU_SENS_PRESS": 9.1,
    "PU_LEVEL_PW_CONTROL": 80,
    "PU_SET_LEVEL_PW_CONTROL": 80,
    "PU_SENS_FLOW_METER_ML": 12.3,
    "SB_SENS_PRESS": 1.2,
    "BB_SENS_TEMP_A": 130.0,
    "BB_LEVEL_PW_CONTROL": 60,
    "SB_STATUS": 2,
    "SCALE_WEIGHT": 18.5,
}

OVERVIEW_SINGLE_PAYLOAD: dict[str, Any] = {
    "BG_SET_TEMP": 93.5,
    "PU_SET_PRESS": 9.0,
    "PU_SENS_WATER_TANK_LEVEL": 1,
    "SB_SET_PRESS": 1.5,
    "BB_SET_TEMP": 130.0,
    "PSP": 0,
    "MA_MAC": "AA:BB:CC:DD:EE:FF",
    "MA_EXTRACTIONS_START": 100,
    "POP_UP": None,
}

MACHINE_PAYLOAD: dict[str, Any] = {
    "MA_TYPE": 1,
    "FW_VERSION_MAJOR": 2,
    "FW_VERSION_MINOR": 3,
    "ESP_FW_MAJOR": 1,
    "ESP_FW_MINOR": 5,
}

SCRIPTS_PAYLOAD: dict[str, Any] = {
    "index_list": [10, 20],
    "title_list": ["MyShot", "Lungo"],
}

SWITCHES_PAYLOAD: dict[str, Any] = {
    "SWITCH_SET_LEFT_LEFT_0": 1,
    "SWITCH_SET_LEFT_LEFT_1": 2,
}


# ---------------------------------------------------------------------------
# Domain-object fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def overview_data() -> XeniaOverviewData:
    """Return a populated XeniaOverviewData."""
    return XeniaOverviewData.from_dict(OVERVIEW_PAYLOAD)


@pytest.fixture
def overview_single_data() -> XeniaOverviewSingleData:
    """Return a populated XeniaOverviewSingleData."""
    return XeniaOverviewSingleData.from_dict(OVERVIEW_SINGLE_PAYLOAD)


@pytest.fixture
def machine_data() -> XeniaMachineData:
    """Return a populated XeniaMachineData."""
    return XeniaMachineData.from_dict(MACHINE_PAYLOAD)


@pytest.fixture
def coordinator_data(
    overview_data: XeniaOverviewData,
    overview_single_data: XeniaOverviewSingleData,
) -> XeniaCoordinatorData:
    """Return a populated XeniaCoordinatorData."""
    return XeniaCoordinatorData(
        overview=overview_data,
        overview_single=overview_single_data,
    )


@pytest.fixture
def config_data(machine_data: XeniaMachineData) -> XeniaConfigData:
    """Return a populated XeniaConfigData with scripts and switches."""
    return XeniaConfigData(
        machine=machine_data,
        scripts={
            0: "None",
            1: "Espresso",
            2: "Espresso endless",
            10: "MyShot",
            20: "Lungo",
        },
        switches={"SWITCH_SET_LEFT_LEFT_0": 1, "SWITCH_SET_LEFT_LEFT_1": 2},
    )


# ---------------------------------------------------------------------------
# Mock aiohttp session
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> MagicMock:
    """Return a mock aiohttp ClientSession."""
    return MagicMock()
