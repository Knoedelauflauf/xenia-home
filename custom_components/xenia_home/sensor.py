"""Sensor platform for the Xenia espresso machine."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
import time
from typing import Final

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONF_HOST,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfEnergy,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.typing import StateType

from .coordinator import (
    XeniaConfigEntry,
    XeniaCoordinatorData,
    XeniaDataUpdateCoordinator,
)
from .entity import XeniaEntity
from .xenia import MachineStatus

PARALLEL_UPDATES = 0

# How long the shot timer keeps showing the last shot's duration after
# brewing stops before it resets to 0.
SHOT_TIMER_IDLE_RESET_SECONDS: Final = 30

# How often the shot timer's displayed value ticks while actively brewing.
# Matches the whole-second display resolution - no point ticking faster.
SHOT_TIMER_TICK_INTERVAL: Final = timedelta(seconds=1)


@dataclass(frozen=True, kw_only=True)
class XeniaEntityDescriptionMixinSensor:
    """Mixin adding a value extractor to a sensor description."""

    value_fn: Callable[[XeniaCoordinatorData], StateType]


@dataclass(frozen=True, kw_only=True)
class XeniaSensorEntityDescription(
    SensorEntityDescription, XeniaEntityDescriptionMixinSensor
):
    """Sensor description with dynamic entity-category and existence resolution."""

    entity_category_fn: (
        Callable[[XeniaCoordinatorData], EntityCategory | None] | None
    ) = None
    exists_fn: Callable[[XeniaCoordinatorData], bool] = lambda data: True


SENSOR_TYPES: Final[tuple[XeniaSensorEntityDescription, ...]] = (
    XeniaSensorEntityDescription(
        key="brew_group_temperature",
        translation_key="brew_group_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
        value_fn=lambda data: data.overview.bg_sens_temp_a,
    ),
    XeniaSensorEntityDescription(
        key="brew_boiler_temperature",
        translation_key="brew_boiler_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-water",
        value_fn=lambda data: data.overview.bb_sens_temp_a,
    ),
    XeniaSensorEntityDescription(
        key="pump_pressure",
        translation_key="pump_pressure",
        native_unit_of_measurement=UnitOfPressure.BAR,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gauge",
        value_fn=lambda data: data.overview.pu_sens_press,
    ),
    XeniaSensorEntityDescription(
        key="steam_boiler_pressure",
        translation_key="steam_boiler_pressure",
        native_unit_of_measurement=UnitOfPressure.BAR,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gauge-full",
        value_fn=lambda data: data.overview.sb_sens_press,
    ),
    XeniaSensorEntityDescription(
        key="electric_current",
        translation_key="electric_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:current-ac",
        value_fn=lambda data: data.overview.ma_cur_pwr,
    ),
    XeniaSensorEntityDescription(
        key="total_energy",
        translation_key="total_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:lightning-bolt",
        value_fn=lambda data: data.overview.ma_energy_total_kwh,
    ),
    XeniaSensorEntityDescription(
        key="extractions",
        translation_key="extractions",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:coffee-to-go",
        value_fn=lambda data: data.overview.ma_extractions,
    ),
    XeniaSensorEntityDescription(
        key="operating_hours",
        translation_key="operating_hours",
        native_unit_of_measurement=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:clock-outline",
        value_fn=lambda data: data.overview.ma_operating_hours / 60,
    ),
    XeniaSensorEntityDescription(
        key="scale_flow_rate",
        translation_key="scale_flow_rate",
        native_unit_of_measurement="g/s",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:scale",
        value_fn=lambda data: data.overview.pu_sens_scale_rate,
        exists_fn=lambda data: data.overview.pu_sens_scale_rate is not None,
    ),
    XeniaSensorEntityDescription(
        key="machine_status",
        translation_key="machine_status",
        device_class=SensorDeviceClass.ENUM,
        options=[status.name.lower() for status in MachineStatus],
        icon="mdi:coffee-maker",
        value_fn=lambda data: data.overview.ma_status.name.lower(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: XeniaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Xenia sensor entities."""
    coordinator = entry.runtime_data.coordinator
    entities: list[SensorEntity] = [
        XeniaSensor(coordinator, description)
        for description in SENSOR_TYPES
        if description.exists_fn(coordinator.data)
    ]
    entities.append(XeniaShotTimerSensor(coordinator))
    async_add_entities(entities)


class XeniaSensor(XeniaEntity, SensorEntity):
    """A sensor backed by `value_fn` against the fast coordinator data."""

    def __init__(
        self,
        coordinator: XeniaDataUpdateCoordinator,
        entity_description: XeniaSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description: XeniaSensorEntityDescription = entity_description
        self._attr_unique_id = (
            f"{coordinator.config_entry.data[CONF_HOST]}_{entity_description.key}"
        )

    @property
    def native_value(self) -> StateType:
        """Return the sensor value, or None for zeroed cumulative counters."""
        value = self.entity_description.value_fn(self.coordinator.data)
        if (
            self.entity_description.state_class == SensorStateClass.TOTAL_INCREASING
            and not value
        ):
            return None
        return value

    @property
    def entity_category(self) -> EntityCategory | None:
        """Resolve the entity category dynamically if `entity_category_fn` is set."""
        if self.entity_description.entity_category_fn is not None:
            return self.entity_description.entity_category_fn(self.coordinator.data)
        return super().entity_category


class XeniaShotTimerSensor(XeniaEntity, SensorEntity):
    """Live shot timer.

    Counts up in whole seconds while `MA_STATUS` is `BREWING`, freezes at
    the final value the moment brewing stops (whether that is `DRAINING`
    or anything else), and resets to 0 either immediately when the machine
    reaches `OFF`/`ECO`, or `SHOT_TIMER_IDLE_RESET_SECONDS` after brewing
    stopped - measured from the end of the shot itself, not from whenever
    `DRAINING` happens to finish, so `DRAINING` gets no "free" extra
    display time beyond the configured delay. `0` is the "no recent shot"
    value (never `unknown`), matching how other espresso machine
    integrations model this.

    Unlike the declarative `XeniaSensor`/`value_fn` sensors above, this
    value cannot be derived from a single coordinator snapshot alone - it
    depends on *when* status transitions happened, so it keeps that
    bookkeeping locally instead of in the coordinator. To show live
    updates without polling the machine any harder, it drives its own
    display refresh via `async_track_time_interval`, independent of the
    coordinator's (much slower) poll interval.
    """

    _attr_translation_key = "shot_timer"
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:timer-outline"

    def __init__(self, coordinator: XeniaDataUpdateCoordinator) -> None:
        """Initialize the shot timer."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.data[CONF_HOST]}_shot_timer"
        self._previous_status: MachineStatus | None = None
        self._start_monotonic: float | None = None
        self._frozen_elapsed: int = 0
        self._tick_unsub: Callable[[], None] | None = None
        self._idle_reset_unsub: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Prime the transition bookkeeping from whatever state we start in."""
        await super().async_added_to_hass()
        current_status = self.coordinator.data.overview.ma_status
        self._handle_status_transition(None, current_status)
        self._previous_status = current_status

    async def async_will_remove_from_hass(self) -> None:
        """Cancel any pending timers so they don't outlive the entity."""
        self._stop_ticking()
        self._cancel_idle_reset()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_coordinator_update(self) -> None:
        """React to a fresh `MA_STATUS` reading from the coordinator."""
        new_status = self.coordinator.data.overview.ma_status
        self._handle_status_transition(self._previous_status, new_status)
        self._previous_status = new_status
        self.async_write_ha_state()

    def _handle_status_transition(
        self, old_status: MachineStatus | None, new_status: MachineStatus
    ) -> None:
        """Update start/freeze/reset bookkeeping for an `old -> new` transition."""
        if old_status == new_status:
            return

        # Cancel any pending reset unconditionally; it gets re-armed below
        # exactly once, at the moment brewing actually stops.
        self._cancel_idle_reset()

        if old_status == MachineStatus.BREWING:
            # Brewing just stopped (regardless of what it stopped into):
            # freeze the last live value instead of letting it keep
            # counting or disappearing immediately.
            self._frozen_elapsed = self._current_elapsed()
            self._start_monotonic = None
            self._stop_ticking()
            # The reset delay is measured from the end of the shot itself,
            # not from whenever DRAINING happens to finish - DRAINING gets
            # no "free" extra display time beyond it. Skip arming it if
            # we're headed straight to OFF/ECO, since those reset
            # immediately below anyway.
            if new_status not in (MachineStatus.OFF, MachineStatus.ECO):
                self._idle_reset_unsub = async_call_later(
                    self.hass, SHOT_TIMER_IDLE_RESET_SECONDS, self._handle_idle_reset
                )

        if new_status == MachineStatus.BREWING:
            self._start_monotonic = time.monotonic()
            self._frozen_elapsed = 0
            self._start_ticking()
        elif new_status in (MachineStatus.OFF, MachineStatus.ECO):
            self._frozen_elapsed = 0
        # MachineStatus.DRAINING / ON / UNKNOWN: keep showing the frozen
        # value until the reset timer armed above fires.

    def _current_elapsed(self) -> int:
        """Return the number of full seconds elapsed, else the frozen value.

        Truncates rather than rounds - like a stopwatch, `3` means "3 full
        seconds have passed", not "closer to 3 than to 4". Rounding would
        make the display jump to the next second early.
        """
        if self._start_monotonic is None:
            return self._frozen_elapsed
        return int(time.monotonic() - self._start_monotonic)

    @callback
    def _handle_idle_reset(self, _now) -> None:
        """Reset to 0 after a sustained idle period."""
        self._idle_reset_unsub = None
        self._frozen_elapsed = 0
        self.async_write_ha_state()

    @callback
    def _cancel_idle_reset(self) -> None:
        if self._idle_reset_unsub is not None:
            self._idle_reset_unsub()
            self._idle_reset_unsub = None

    @callback
    def _start_ticking(self) -> None:
        if self._tick_unsub is None:
            self._tick_unsub = async_track_time_interval(
                self.hass, self._handle_tick, SHOT_TIMER_TICK_INTERVAL
            )

    @callback
    def _stop_ticking(self) -> None:
        if self._tick_unsub is not None:
            self._tick_unsub()
            self._tick_unsub = None

    @callback
    def _handle_tick(self, _now) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> StateType:
        """Return the current or frozen shot duration in seconds."""
        return self._current_elapsed()
