"""Persistent shot history: slim index plus one chunk file per month."""

import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import XENIA_DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
SUMMARY_KEYS = (
    "shot_id",
    "start_time",
    "brew_end_time",
    "duration_seconds",
    "final_weight_g",
)


class XeniaShotStore:
    """Stores completed shots; the payload shape is the shot_completed event data."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize the store for one config entry; call async_load next."""
        self._hass = hass
        self._entry_id = entry_id
        self._index_store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{XENIA_DOMAIN}.{entry_id}.shots_index"
        )
        self._index: dict[str, Any] = {"migrated": False, "shots": []}
        self._chunks: dict[str, dict[str, Any]] = {}
        self._chunk_stores: dict[str, Store[dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

    async def async_load(self) -> None:
        """Load the index; a corrupt file must never block integration setup."""
        try:
            data = await self._index_store.async_load()
        except Exception:
            _LOGGER.exception("Shot index unreadable; starting with empty history")
            data = None
        if data is not None:
            self._index = data

    @property
    def migrated(self) -> bool:
        """Whether the one-time recorder import has already run."""
        return self._index["migrated"]

    async def async_set_migrated(self) -> None:
        """Mark the one-time recorder import as done."""
        async with self._lock:
            self._index["migrated"] = True
            await self._index_store.async_save(self._index)

    def _chunk_store(self, month: str) -> Store[dict[str, Any]]:
        return self._chunk_stores.setdefault(
            month,
            Store(
                self._hass,
                STORAGE_VERSION,
                f"{XENIA_DOMAIN}.{self._entry_id}.shots_{month}",
            ),
        )

    async def _load_chunk(self, month: str) -> dict[str, Any]:
        if month not in self._chunks:
            try:
                loaded = await self._chunk_store(month).async_load() or {}
            except Exception:
                _LOGGER.exception("Shot chunk %s unreadable; treating as empty", month)
                loaded = {}
            # A concurrent add for the same month may have already populated
            # this from a fresh save; keep that winner instead of overwriting
            # it with our (now stale) pre-add snapshot.
            self._chunks.setdefault(month, loaded)
        return self._chunks[month]

    @staticmethod
    def _month(shot_id: str) -> str | None:
        # The shot_id doubles as part of a storage key; only accept real
        # timestamps so a crafted id cannot escape the storage directory.
        if dt_util.parse_datetime(shot_id) is None:
            return None
        return shot_id[:7]

    async def async_add_shot(self, payload: dict[str, Any]) -> None:
        """Persist a completed shot, ignoring duplicates by start_time."""
        shot_id = payload["start_time"]
        month = self._month(shot_id)
        if month is None:
            _LOGGER.warning("Ignoring shot with unparseable start_time: %s", shot_id)
            return
        async with self._lock:
            if any(s["shot_id"] == shot_id for s in self._index["shots"]):
                return
            chunk = await self._load_chunk(month)
            chunk[shot_id] = payload
            weights = payload.get("weights") or []
            self._index["shots"].append(
                {
                    "shot_id": shot_id,
                    "start_time": shot_id,
                    "brew_end_time": payload.get("brew_end_time"),
                    "duration_seconds": payload.get("duration_seconds"),
                    "final_weight_g": weights[-1] if weights else None,
                    "month": month,
                }
            )
            await self._chunk_store(month).async_save(chunk)
            await self._index_store.async_save(self._index)

    @callback
    def list_shots(self) -> list[dict[str, Any]]:
        """Summaries, newest first, without the internal month key."""
        ordered = sorted(
            self._index["shots"], key=lambda s: s["start_time"], reverse=True
        )
        return [{key: shot[key] for key in SUMMARY_KEYS} for shot in ordered]

    async def async_get_shots(self, shot_ids: list[str]) -> list[dict[str, Any]]:
        """Full payloads in request order; unknown ids are omitted."""
        known_months = {s["month"] for s in self._index["shots"]}
        result = []
        for shot_id in shot_ids:
            month = self._month(shot_id)
            if month is None or month not in known_months:
                continue
            payload = (await self._load_chunk(month)).get(shot_id)
            if payload is not None:
                result.append({**payload, "shot_id": shot_id})
        return result

    async def async_delete_shot(self, shot_id: str) -> bool:
        """Delete a shot by id; return whether it existed."""
        month = self._month(shot_id)
        if month is None:
            return False
        async with self._lock:
            shots = self._index["shots"]
            remaining = [s for s in shots if s["shot_id"] != shot_id]
            if len(remaining) == len(shots):
                return False
            self._index["shots"] = remaining
            chunk = await self._load_chunk(month)
            chunk.pop(shot_id, None)
            if chunk:
                await self._chunk_store(month).async_save(chunk)
            else:
                await self._chunk_store(month).async_remove()
                self._chunks.pop(month, None)
                self._chunk_stores.pop(month, None)
            await self._index_store.async_save(self._index)
            return True

    async def async_remove(self) -> None:
        """Delete every storage file belonging to this entry."""
        async with self._lock:
            for month in {s["month"] for s in self._index["shots"]}:
                await self._chunk_store(month).async_remove()
            await self._index_store.async_remove()
            self._index = {"migrated": False, "shots": []}
            self._chunks = {}
            self._chunk_stores = {}
