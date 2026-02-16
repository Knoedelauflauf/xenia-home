"""Event platform for Xenia espresso machine shot tracking."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import XENIA_DOMAIN
from .coordinator import XeniaConfigEntry, XeniaDataUpdateCoordinator
from .entity import XeniaEntity
from .xenia import MachineStatus

_LOGGER = logging.getLogger(__name__)


@dataclass
class ShotData:
    """Raw data structure for a single espresso shot."""

    start_time: str
    brew_end_time: str | None
    afterflow_seconds: int
    duration_seconds: float
    timestamps: list[float]
    brew_group_temps: list[float]
    brew_boiler_temps: list[float]
    pump_pressures: list[float]
    flow_rates: list[float]
    weights: list[float]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: XeniaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Xenia event entities."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities([XeniaShotTracker(coordinator)])


class XeniaShotTracker(XeniaEntity, EventEntity):
    """Event entity that tracks espresso shots and fires events with shot data."""

    _attr_translation_key = "shot_tracker"
    _attr_event_types = ["shot_completed"]
    _afterflow_seconds = 2
    _min_shot_seconds = 10

    def __init__(self, coordinator: XeniaDataUpdateCoordinator) -> None:
        """Initialize the shot tracker."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{XENIA_DOMAIN}_shot_tracker_"
            f"{coordinator.config_entry.data[CONF_HOST]}"
        )
        self._is_brewing = False
        self._shot_start_time: datetime | None = None
        self._brew_group_temps: list[float] = []
        self._brew_boiler_temps: list[float] = []
        self._pump_pressures: list[float] = []
        self._flow_rates: list[float] = []
        self._weights: list[float] = []
        self._timestamps: list[float] = []
        self._afterflow_until: datetime | None = None
        self._afterflow_samples = 0
        self._brew_end_time: datetime | None = None

    async def async_added_to_hass(self) -> None:
        """Subscribe to coordinator updates when added to hass."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle coordinator updates to track brewing sessions."""
        data = self.coordinator.data
        current_status = data.overview.ma_status
        is_currently_brewing = current_status == MachineStatus.BREWING
        if is_currently_brewing and not self._is_brewing:
            self._cancel_afterflow()
            self._start_shot_tracking()
        elif is_currently_brewing and self._is_brewing:
            self._collect_shot_data()
        elif not is_currently_brewing and self._is_brewing:
            self._start_afterflow()
            self._collect_shot_data()
        elif self._afterflow_until is not None:
            self._collect_shot_data()
            if datetime.now() >= self._afterflow_until:
                self._complete_shot_tracking()

        self._is_brewing = is_currently_brewing
        self.async_write_ha_state()

    def _start_shot_tracking(self) -> None:
        """Start tracking a new shot."""
        self._shot_start_time = datetime.now()
        self._brew_end_time = None
        self._brew_group_temps = []
        self._brew_boiler_temps = []
        self._pump_pressures = []
        self._flow_rates = []
        self._weights = []
        self._timestamps = []
        _LOGGER.debug("Started tracking new espresso shot")

    def _start_afterflow(self) -> None:
        """Start a short afterflow window to capture drips."""
        if self._afterflow_until is not None:
            return
        self._brew_end_time = datetime.now()
        self._afterflow_until = datetime.now() + timedelta(
            seconds=self._afterflow_seconds
        )
        self._afterflow_samples = 0

    def _cancel_afterflow(self) -> None:
        """Cancel any active afterflow task."""
        self._afterflow_until = None
        self._afterflow_samples = 0

    def _collect_shot_data(self) -> None:
        """Collect data point during brewing."""
        if self._shot_start_time is None:
            return

        data = self.coordinator.data
        elapsed = (datetime.now() - self._shot_start_time).total_seconds()
        if not self._is_brewing and self._afterflow_until is not None:
            self._afterflow_samples += 1

        self._brew_group_temps.append(data.overview.bg_sens_temp_a)
        self._brew_boiler_temps.append(data.overview.bb_sens_temp_a)
        self._pump_pressures.append(data.overview.pu_sens_press)
        self._flow_rates.append(data.overview.pu_sens_flow_meter_ml)
        self._weights.append(data.overview.scale_weight)
        self._timestamps.append(elapsed)

    def _complete_shot_tracking(self) -> None:
        """Complete shot tracking and fire event with data."""
        if self._shot_start_time is None or not self._timestamps:
            _LOGGER.warning("Shot ended but no data was collected")
            return
        self._cancel_afterflow()

        end_time = datetime.now()
        if self._brew_end_time is not None:
            duration = (self._brew_end_time - self._shot_start_time).total_seconds()
        else:
            duration = (end_time - self._shot_start_time).total_seconds()
        if duration < self._min_shot_seconds:
            _LOGGER.debug(
                "Ignoring short shot: duration=%.2fs (< %ss)",
                duration,
                self._min_shot_seconds,
            )
            return

        shot_data = ShotData(
            start_time=self._shot_start_time.isoformat(),
            brew_end_time=(
                self._brew_end_time.isoformat() if self._brew_end_time else None
            ),
            afterflow_seconds=self._afterflow_seconds,
            duration_seconds=round(duration, 2),
            timestamps=self._timestamps,
            brew_group_temps=self._brew_group_temps,
            brew_boiler_temps=self._brew_boiler_temps,
            pump_pressures=self._pump_pressures,
            flow_rates=self._flow_rates,
            weights=self._weights,
        )

        self._trigger_event("shot_completed", shot_data.to_dict())

        final_weight = self._weights[-1] if self._weights else 0.0
        _LOGGER.info(
            "Shot completed: duration=%.1fs, weight=%.1fg",
            duration,
            final_weight,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        return {"is_brewing": self._is_brewing}
