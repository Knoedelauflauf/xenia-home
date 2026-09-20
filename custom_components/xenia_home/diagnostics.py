"""Diagnostics for the Xenia espresso machine."""

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .coordinator import XeniaConfigEntry

TO_REDACT = {CONF_HOST, "ma_sn", "ma_mac"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: XeniaConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime = entry.runtime_data
    data = runtime.coordinator.data
    return async_redact_data(
        {
            "entry": {"data": dict(entry.data), "options": dict(entry.options)},
            "overview": asdict(data.overview),
            "overview_single": asdict(data.overview_single),
            "config": asdict(runtime.config_coordinator.data),
            "power_on_behavior": runtime.power_on_behavior,
            "shot_count": len(runtime.shot_store.list_shots()),
        },
        TO_REDACT,
    )
