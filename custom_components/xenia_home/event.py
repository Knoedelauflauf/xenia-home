"""Event platform for Xenia espresso machine shot tracking."""

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import logging
from typing import Any, override

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import XeniaConfigEntry, XeniaDataUpdateCoordinator
from .entity import XeniaEntity
from .xenia import MachineStatus

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


@dataclass
class ShotData:
    """The curves of one shot, as fired with shot_completed."""

    start_time: str
    brew_end_time: str
    afterflow_seconds: int
    duration_seconds: float
    timestamps: list[float]
    brew_group_temps: list[float]
    brew_boiler_temps: list[float]
    pump_pressures: list[float]
    flow_rates: list[float]
    weights: list[float]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: XeniaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the shot tracker."""
    async_add_entities([XeniaShotTracker(entry.runtime_data.coordinator)])


class XeniaShotTracker(XeniaEntity, EventEntity):
    """Record the curves of every shot and fire shot_completed when it ends."""

    _attr_translation_key = "shot_tracker"
    _attr_event_types = ["shot_completed"]
    _afterflow_seconds = 2
    _min_shot_seconds = 10
    _tare_drop_g = 2.0
    # Curve arrays stay out of the recorder DB; history is served by the
    # integration's own shot store, so only the scalars need persisting.
    _unrecorded_attributes = frozenset(
        {
            "timestamps",
            "brew_group_temps",
            "brew_boiler_temps",
            "pump_pressures",
            "flow_rates",
            "weights",
        }
    )

    def __init__(self, coordinator: XeniaDataUpdateCoordinator) -> None:
        """Initialize the shot tracker."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{self.machine_id}_shot_tracker"
        self._is_brewing = False
        self._shot_start_time: datetime | None = None
        self._brew_group_temps: list[float] = []
        self._brew_boiler_temps: list[float] = []
        self._pump_pressures: list[float] = []
        self._flow_rates: list[float] = []
        self._weights: list[float] = []
        self._timestamps: list[float] = []
        self._afterflow_until: datetime | None = None
        self._brew_end_time: datetime | None = None

    @callback
    @override
    def _handle_coordinator_update(self) -> None:
        """Follow the brewing state of the machine."""
        if not self.coordinator.last_update_success:
            # The data is the last answer of the machine, not a new sample.
            self.async_write_ha_state()
            return
        is_currently_brewing = (
            self.coordinator.data.overview.ma_status is MachineStatus.BREWING
        )
        if (
            is_currently_brewing
            and self.coordinator.data.shot_start_time != self._shot_start_time
        ):
            if self._is_brewing:
                # The last brew ended during an outage.
                self._start_afterflow()
            if self._afterflow_until is not None:
                self._complete_shot_tracking()
            self._start_shot_tracking()
        elif is_currently_brewing:
            self._collect_shot_data()
        else:
            if self._is_brewing:
                self._start_afterflow()
            if self._afterflow_until is not None:
                if dt_util.utcnow() <= self._afterflow_until:
                    self._collect_shot_data()
                if (
                    self._afterflow_until is not None
                    and dt_util.utcnow() >= self._afterflow_until
                ):
                    self._complete_shot_tracking()

        self._is_brewing = is_currently_brewing
        self.async_write_ha_state()

    def _start_shot_tracking(self) -> None:
        """Start recording a new shot."""
        self._shot_start_time = self.coordinator.data.shot_start_time
        self._brew_end_time = None
        self._brew_group_temps = []
        self._brew_boiler_temps = []
        self._pump_pressures = []
        self._flow_rates = []
        self._weights = []
        self._timestamps = []

    def _start_afterflow(self) -> None:
        """Keep recording for a moment after brewing to catch the drips."""
        self._brew_end_time = self.coordinator.data.brew_end_time
        assert self._brew_end_time is not None
        self._afterflow_until = self._brew_end_time + timedelta(
            seconds=self._afterflow_seconds
        )

    def _collect_shot_data(self) -> None:
        """Record one sample of the curves."""
        assert self._shot_start_time is not None
        overview = self.coordinator.data.overview
        # Firmware with scale support reports no usable flow meter data;
        # the scale rate replaces it as the flow source.
        flow = (
            overview.pu_sens_scale_rate
            if overview.pu_sens_scale_rate is not None
            else overview.pu_sens_flow_meter_ml
        )
        group_temp = overview.bg_sens_temp_a
        boiler_temp = overview.bb_sens_temp_a
        pressure = overview.pu_sens_press
        weight = overview.scale_weight
        if weight is None:
            # A missing weight must neither drop the sample nor look like a tare.
            weight = self._weights[-1] if self._weights else 0.0
        if (
            group_temp is None
            or boiler_temp is None
            or pressure is None
            or flow is None
        ):
            return

        # A big drop is a tare (or the cup being moved), never real outflow.
        if self._weights and weight < self._weights[-1] - self._tare_drop_g:
            if self._afterflow_until is not None:
                self._complete_shot_tracking()
                return
            self._weights = [0.0] * len(self._weights)

        elapsed = (dt_util.utcnow() - self._shot_start_time).total_seconds()
        self._brew_group_temps.append(group_temp)
        self._brew_boiler_temps.append(boiler_temp)
        self._pump_pressures.append(pressure)
        self._flow_rates.append(flow)
        self._weights.append(weight)
        self._timestamps.append(elapsed)

    def _complete_shot_tracking(self) -> None:
        """Fire shot_completed and store the shot, unless it was too short or empty."""
        assert self._shot_start_time is not None
        assert self._brew_end_time is not None
        self._afterflow_until = None

        duration = (self._brew_end_time - self._shot_start_time).total_seconds()
        if not self._timestamps or duration < self._min_shot_seconds:
            _LOGGER.debug(
                "Ignoring shot: duration=%.2fs, %d samples",
                duration,
                len(self._timestamps),
            )
            return

        # Millisecond precision keeps the strings inside the ECMAScript
        # date-time grammar so frontends can parse them with new Date(...).
        shot_data = ShotData(
            start_time=self._shot_start_time.isoformat(timespec="milliseconds"),
            brew_end_time=self._brew_end_time.isoformat(timespec="milliseconds"),
            afterflow_seconds=self._afterflow_seconds,
            duration_seconds=round(duration, 2),
            timestamps=self._timestamps,
            brew_group_temps=self._brew_group_temps,
            brew_boiler_temps=self._brew_boiler_temps,
            pump_pressures=self._pump_pressures,
            flow_rates=self._flow_rates,
            weights=self._weights,
        )

        payload = asdict(shot_data)
        self._trigger_event("shot_completed", payload)
        self.coordinator.config_entry.async_create_task(
            self.hass,
            self.runtime_data.shot_store.async_add_shot(payload),
        )

        _LOGGER.debug(
            "Shot completed: duration=%.1fs, weight=%.1fg",
            duration,
            self._weights[-1],
        )

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return whether a shot is being brewed."""
        return {"is_brewing": self._is_brewing}
