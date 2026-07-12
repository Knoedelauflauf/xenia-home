"""Canonical Xenia API JSON payloads used across the test suite.

Each payload mirrors what the real machine returns from the corresponding
endpoint. Tests modify copies of these via dict-spread to override
specific fields.
"""

from typing import Any

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

# Extra keys firmware 4.159 adds on top of the old payloads. Tests spread
# these over the canonical payloads to simulate a new-firmware machine.
OVERVIEW_NEW_FW_FIELDS: dict[str, Any] = {
    "MA_LAST_EXTRACTION_ML": "",
    "MA_SET_TIMER_POWERDOWN": 10,
    "PU_SENS_SCALE_VOLUME": 18.5,
    "PU_SENS_SCALE_RATE": 1.27,
    "PU_SENS_FLOW_METER_VOLUME": 0,
    "PU_SENS_FLOW_METER_FLOWRATE": 0,
}

MACHINE_NEW_FW_FIELDS: dict[str, Any] = {
    "MA_SN": "300200000000",
    "MA_MAX_AMPERE": 10,
    "MA_SET_TIMER_ECO_MA": 5,
    "MA_SET_TIMER_POWERDOWN": 10,
}
