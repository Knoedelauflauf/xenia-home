"""One-time best-effort import of shots the recorder still holds."""

import asyncio
from datetime import timedelta
from functools import partial
import logging
from typing import Any

from homeassistant.components.recorder import get_instance, history
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.start import async_at_started
from homeassistant.util import dt as dt_util

from .shot_store import XeniaShotStore

_LOGGER = logging.getLogger(__name__)

_PAYLOAD_KEYS = (
    "start_time",
    "brew_end_time",
    "afterflow_seconds",
    "duration_seconds",
    "timestamps",
    "brew_group_temps",
    "brew_boiler_temps",
    "pump_pressures",
    "flow_rates",
    "weights",
)


async def async_import_recorder_shots(
    hass: HomeAssistant, entry: ConfigEntry, store: XeniaShotStore
) -> None:
    """Copy completed shots from recorder history into the store, then never again."""
    # The recorder may still be starting up during HA boot; only after HA has
    # fully started is its presence in hass.config.components authoritative.
    started = asyncio.Event()

    @callback
    def _resume(_hass: HomeAssistant) -> None:
        started.set()

    async_at_started(hass, _resume)
    await started.wait()

    try:
        if "recorder" in hass.config.components and (
            entity_id := _tracker_entity_id(hass, entry)
        ):
            for payload in await _legacy_shots(hass, entity_id):
                await store.async_add_shot(payload)
    except Exception:
        _LOGGER.exception("One-time shot import from the recorder failed")
    # Deliberately not in a finally: cancellation (unload/restart) must not
    # mark the import done; it retries next boot and async_add_shot dedupes.
    await store.async_set_migrated()


@callback
def _tracker_entity_id(hass: HomeAssistant, entry: ConfigEntry) -> str | None:
    registry = er.async_get(hass)
    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg_entry.domain == "event":
            return reg_entry.entity_id
    return None


async def _legacy_shots(hass: HomeAssistant, entity_id: str) -> list[dict[str, Any]]:
    states = await get_instance(hass).async_add_executor_job(
        partial(
            history.get_significant_states,
            hass,
            dt_util.utcnow() - timedelta(days=400),
            None,
            [entity_id],
            significant_changes_only=False,
        )
    )
    # Old versions recorded one row per attribute change with growing arrays;
    # only the last row per start_time holds the complete shot.
    shots: dict[str, dict[str, Any]] = {}
    for state in states.get(entity_id, []):
        if not isinstance(state, State):
            continue
        attrs = state.attributes
        if attrs.get("event_type") != "shot_completed":
            continue
        payload = {key: attrs[key] for key in _PAYLOAD_KEYS if key in attrs}
        if not payload.get("start_time") or not payload.get("timestamps"):
            continue
        shots[payload["start_time"]] = payload
    return [shots[key] for key in sorted(shots)]
