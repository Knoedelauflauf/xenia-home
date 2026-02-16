from enum import Enum

XENIA_DOMAIN = "xenia_home"
PLATFORMS = ["binary_sensor", "button", "event", "number", "select", "sensor", "switch"]
DEFAULT_HOST = "xenia.local"

CONF_POWER_ON_BEHAVIOR = "power_on_behavior"


class PowerOnBehavior(str, Enum):
    STEAM_ON = "steam_on"
    STEAM_OFF = "steam_off"
    # REMEMBER_LAST = "remember_last"


POWER_ON_BEHAVIOR_OPTIONS: list[PowerOnBehavior] = [e.value for e in PowerOnBehavior]

DEFAULT_POWER_ON_BEHAVIOR = PowerOnBehavior.STEAM_OFF
