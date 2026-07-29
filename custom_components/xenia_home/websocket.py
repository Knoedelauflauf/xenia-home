"""WebSocket API exposing the persistent shot history."""

from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util
import voluptuous as vol

from .const import XENIA_DOMAIN
from .shot_store import XeniaShotStore


@callback
def async_register_commands(hass: HomeAssistant) -> None:
    """Register the shot history commands (once per HA run)."""
    websocket_api.async_register_command(hass, ws_list_shots)
    websocket_api.async_register_command(hass, ws_get_shots)
    websocket_api.async_register_command(hass, ws_delete_shot)


@callback
def _resolve_store(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> XeniaShotStore | None:
    """Return the addressed entry's store, or send an error and return None."""
    entries = hass.config_entries.async_loaded_entries(XENIA_DOMAIN)
    if (entry_id := msg.get("entry_id")) is not None:
        entry = next((e for e in entries if e.entry_id == entry_id), None)
        if entry is None:
            connection.send_error(
                msg["id"],
                "entry_not_found",
                f"No loaded {XENIA_DOMAIN} entry {entry_id}",
            )
            return None
        return entry.runtime_data.shot_store
    if not entries:
        connection.send_error(
            msg["id"], "entry_not_found", f"No loaded {XENIA_DOMAIN} entry"
        )
        return None
    if len(entries) > 1:
        connection.send_error(
            msg["id"], "multiple_entries", "Several entries are loaded; pass entry_id"
        )
        return None
    return entries[0].runtime_data.shot_store


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{XENIA_DOMAIN}/shots/list",
        vol.Optional("entry_id"): str,
        vol.Optional("after"): str,
        vol.Optional("before"): str,
        vol.Optional("limit"): vol.All(int, vol.Range(min=1)),
    }
)
@websocket_api.async_response
async def ws_list_shots(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """List shot summaries, newest first."""
    if (store := _resolve_store(hass, connection, msg)) is None:
        return
    bounds = {}
    for key in ("after", "before"):
        if key in msg:
            parsed = dt_util.parse_datetime(msg[key])
            if parsed is None:
                connection.send_error(
                    msg["id"], "invalid_timestamp", f"Unparseable {key}: {msg[key]}"
                )
                return
            bounds[key] = dt_util.as_utc(parsed)

    shots = store.list_shots()
    if bounds:
        shots = [
            shot
            for shot in shots
            if (start := dt_util.parse_datetime(shot["start_time"])) is not None
            and ("after" not in bounds or start > bounds["after"])
            and ("before" not in bounds or start < bounds["before"])
        ]
    if (limit := msg.get("limit")) is not None:
        shots = shots[:limit]
    connection.send_result(msg["id"], {"shots": shots})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{XENIA_DOMAIN}/shots/get",
        vol.Optional("entry_id"): str,
        vol.Required("shot_ids"): vol.All([str], vol.Length(min=1)),
    }
)
@websocket_api.async_response
async def ws_get_shots(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return full shot payloads in request order; unknown ids are omitted."""
    if (store := _resolve_store(hass, connection, msg)) is None:
        return
    connection.send_result(
        msg["id"], {"shots": await store.async_get_shots(msg["shot_ids"])}
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{XENIA_DOMAIN}/shots/delete",
        vol.Optional("entry_id"): str,
        vol.Required("shot_id"): str,
    }
)
@websocket_api.async_response
async def ws_delete_shot(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Delete a single shot."""
    if (store := _resolve_store(hass, connection, msg)) is None:
        return
    if await store.async_delete_shot(msg["shot_id"]):
        connection.send_result(msg["id"])
    else:
        connection.send_error(
            msg["id"], "not_found", f"Unknown shot_id {msg['shot_id']}"
        )
