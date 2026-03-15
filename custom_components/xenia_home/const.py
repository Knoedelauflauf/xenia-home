from enum import Enum

XENIA_DOMAIN = "xenia_home"
PLATFORMS = ["binary_sensor", "button", "event", "number", "select", "sensor", "switch"]
DEFAULT_HOST = "xenia.local"

CONF_POWER_ON_BEHAVIOR = "power_on_behavior"
CONF_WEIGHT_MANAGEMENT_ENABLED = "weight_management_enabled"
CONF_MANAGED_SCRIPT_ID = "managed_script_id"
CONF_WEIGHT_MIN = "weight_min"
CONF_WEIGHT_MAX = "weight_max"
CONF_WEIGHT_STEP = "weight_step"
DEFAULT_WEIGHT_MIN = 25.0
DEFAULT_WEIGHT_MAX = 50.0
DEFAULT_WEIGHT_STEP = 0.5
DEFAULT_SCRIPT_NAME = "HA Espresso"
DEFAULT_SCRIPT_INSTRUCTION = "1;13;3 70 5000;12 5000;27 40;17;7;"


class PowerOnBehavior(str, Enum):
    STEAM_ON = "steam_on"
    STEAM_OFF = "steam_off"
    # REMEMBER_LAST = "remember_last"


POWER_ON_BEHAVIOR_OPTIONS: list[str] = [e.value for e in PowerOnBehavior]

DEFAULT_POWER_ON_BEHAVIOR = PowerOnBehavior.STEAM_OFF
