"""Constants for the Xenia espresso machine integration."""

from enum import StrEnum

from homeassistant.const import Platform

XENIA_DOMAIN = "xenia_home"
PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.EVENT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]
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

CONF_SHOT_TIMER_IDLE_RESET = "shot_timer_idle_reset"
DEFAULT_SHOT_TIMER_IDLE_RESET = 30

# Pump pressure (bar) the shot timer waits for before it starts counting,
# once BREWING begins. 0 means "start immediately", skipping the wait.
CONF_SHOT_TIMER_START_PRESSURE = "shot_timer_start_pressure"
DEFAULT_SHOT_TIMER_START_PRESSURE = 0.0

CONF_CONFIGURE_POLLING = "configure_polling"
CONF_POLL_BREWING = "poll_interval_brewing"
CONF_POLL_ACTIVE = "poll_interval_active"
CONF_POLL_READY = "poll_interval_ready"
CONF_POLL_IDLE = "poll_interval_idle"
CONF_READY_THRESHOLD = "ready_threshold"
DEFAULT_POLL_BREWING = 1.0
DEFAULT_POLL_ACTIVE = 1.0
DEFAULT_POLL_READY = 1.0
DEFAULT_POLL_IDLE = 1.0
DEFAULT_READY_THRESHOLD = 2.0

POLLING_OPTION_KEYS = (
    CONF_POLL_BREWING,
    CONF_POLL_ACTIVE,
    CONF_POLL_READY,
    CONF_POLL_IDLE,
    CONF_READY_THRESHOLD,
)


class PowerOnBehavior(StrEnum):
    """Whether the steam boiler turns on with the machine."""

    STEAM_ON = "steam_on"
    STEAM_OFF = "steam_off"
    # REMEMBER_LAST = "remember_last"


POWER_ON_BEHAVIOR_OPTIONS: list[str] = [e.value for e in PowerOnBehavior]

DEFAULT_POWER_ON_BEHAVIOR = PowerOnBehavior.STEAM_OFF.value
