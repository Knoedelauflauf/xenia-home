"""Contract tests for the persistent shot store."""

from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store

from custom_components.xenia_home.const import XENIA_DOMAIN
from custom_components.xenia_home.shot_store import XeniaShotStore

from tests.fixtures.shots import shot_payload

ENTRY_ID = "test_entry"


async def _loaded_store(
    hass: HomeAssistant, entry_id: str = ENTRY_ID
) -> XeniaShotStore:
    store = XeniaShotStore(hass, entry_id)
    await store.async_load()
    return store


async def test_added_shot_is_listed_and_retrievable(hass: HomeAssistant) -> None:
    """An added shot is listed as a summary and returned in full."""
    store = await _loaded_store(hass)
    payload = shot_payload()
    await store.async_add_shot(payload)

    summaries = store.list_shots()
    assert summaries == [
        {
            "shot_id": payload["start_time"],
            "start_time": payload["start_time"],
            "brew_end_time": payload["brew_end_time"],
            "duration_seconds": payload["duration_seconds"],
            "final_weight_g": payload["weights"][-1],
        }
    ]
    shots = await store.async_get_shots([payload["start_time"]])
    assert shots == [{**payload, "shot_id": payload["start_time"]}]


async def test_list_is_newest_first_across_months(hass: HomeAssistant) -> None:
    """Shots of different months are listed newest first and returned together."""
    store = await _loaded_store(hass)
    old = shot_payload("2026-06-15T08:00:00.000+00:00")
    new = shot_payload("2026-07-01T10:00:00.000+00:00")
    await store.async_add_shot(old)
    await store.async_add_shot(new)
    assert [s["shot_id"] for s in store.list_shots()] == [
        new["start_time"],
        old["start_time"],
    ]
    # chunking is invisible: both shots retrievable together, request order kept
    shots = await store.async_get_shots([old["start_time"], new["start_time"]])
    assert [s["shot_id"] for s in shots] == [old["start_time"], new["start_time"]]


async def test_history_survives_reload(hass: HomeAssistant) -> None:
    """Shots are stored on disk."""
    store = await _loaded_store(hass)
    payload = shot_payload()
    await store.async_add_shot(payload)

    reloaded = await _loaded_store(hass)
    assert [s["shot_id"] for s in reloaded.list_shots()] == [payload["start_time"]]
    shots = await reloaded.async_get_shots([payload["start_time"]])
    assert shots[0]["weights"] == payload["weights"]


async def test_duplicate_add_is_ignored(hass: HomeAssistant) -> None:
    """A shot is stored once per start time."""
    store = await _loaded_store(hass)
    await store.async_add_shot(shot_payload())
    await store.async_add_shot(shot_payload())
    assert len(store.list_shots()) == 1


async def test_get_omits_unknown_ids(hass: HomeAssistant) -> None:
    """Unknown or malformed ids are skipped."""
    store = await _loaded_store(hass)
    payload = shot_payload()
    await store.async_add_shot(payload)
    shots = await store.async_get_shots(
        ["2020-01-01T00:00:00.000+00:00", payload["start_time"], "../evil"]
    )
    assert [s["shot_id"] for s in shots] == [payload["start_time"]]


async def test_delete_removes_only_target_and_persists(hass: HomeAssistant) -> None:
    """Deleting removes only that shot, on disk too, and reports whether it existed."""
    store = await _loaded_store(hass)
    keep = shot_payload("2026-07-01T10:00:00.000+00:00")
    drop = shot_payload("2026-07-02T10:00:00.000+00:00")
    await store.async_add_shot(keep)
    await store.async_add_shot(drop)

    assert await store.async_delete_shot(drop["start_time"]) is True
    assert await store.async_delete_shot(drop["start_time"]) is False
    assert await store.async_delete_shot("../evil") is False

    reloaded = await _loaded_store(hass)
    assert [s["shot_id"] for s in reloaded.list_shots()] == [keep["start_time"]]


async def test_remove_deletes_everything(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Removing the store deletes all its files."""
    store = await _loaded_store(hass)
    await store.async_add_shot(shot_payload("2026-06-15T08:00:00.000+00:00"))
    await store.async_add_shot(shot_payload("2026-07-01T10:00:00.000+00:00"))
    await store.async_remove()

    reloaded = await _loaded_store(hass)
    assert reloaded.list_shots() == []
    assert not any(k.startswith(f"{XENIA_DOMAIN}/") for k in hass_storage)


async def test_entries_are_isolated(hass: HomeAssistant) -> None:
    """Each machine has its own history."""
    store_a = await _loaded_store(hass, "entry_a")
    store_b = await _loaded_store(hass, "entry_b")
    await store_a.async_add_shot(shot_payload())
    assert store_b.list_shots() == []


async def test_migrated_flag_persists(hass: HomeAssistant) -> None:
    """The finished recorder import is remembered on disk."""
    store = await _loaded_store(hass)
    assert store.migrated is False
    await store.async_set_migrated()

    reloaded = await _loaded_store(hass)
    assert reloaded.migrated is True


async def test_corrupt_index_is_tolerated(hass: HomeAssistant) -> None:
    """An unreadable index starts an empty, usable history."""
    with patch.object(Store, "async_load", side_effect=HomeAssistantError("corrupt")):
        store = await _loaded_store(hass)
    assert store.list_shots() == []

    payload = shot_payload()
    await store.async_add_shot(payload)
    assert [s["shot_id"] for s in store.list_shots()] == [payload["start_time"]]


async def test_malformed_index_starts_empty(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """An index of the wrong shape starts an empty, usable history."""
    hass_storage[f"{XENIA_DOMAIN}/{ENTRY_ID}.shots_index"] = {
        "version": 1,
        "data": {"bogus": 1},
    }
    store = await _loaded_store(hass)
    assert store.list_shots() == []
    assert store.migrated is False

    payload = shot_payload()
    await store.async_add_shot(payload)
    assert [s["shot_id"] for s in store.list_shots()] == [payload["start_time"]]


async def test_corrupt_chunk_is_tolerated(hass: HomeAssistant) -> None:
    """An unreadable month file loses only its shots."""
    store = await _loaded_store(hass)
    payload = shot_payload()
    await store.async_add_shot(payload)

    reloaded = await _loaded_store(hass)
    with patch.object(Store, "async_load", side_effect=HomeAssistantError("corrupt")):
        assert await reloaded.async_get_shots([payload["start_time"]]) == []

    # store remains usable after the corrupt read
    assert [s["shot_id"] for s in reloaded.list_shots()] == [payload["start_time"]]
    other = shot_payload("2026-08-01T10:00:00.000+00:00")
    await reloaded.async_add_shot(other)
    assert {s["shot_id"] for s in reloaded.list_shots()} == {
        payload["start_time"],
        other["start_time"],
    }


async def test_add_shot_with_unparseable_start_time_is_ignored(
    hass: HomeAssistant,
) -> None:
    """A shot without a valid start time is not stored."""
    store = await _loaded_store(hass)
    await store.async_add_shot(shot_payload(start_time="not-a-timestamp"))
    assert store.list_shots() == []


async def test_delete_last_shot_of_month_removes_chunk_file(
    hass: HomeAssistant,
) -> None:
    """Deleting the last shot of a month removes its file."""
    store = await _loaded_store(hass)
    june = shot_payload("2026-06-15T08:00:00.000+00:00")
    july = shot_payload("2026-07-01T10:00:00.000+00:00")
    await store.async_add_shot(june)
    await store.async_add_shot(july)

    assert await store.async_delete_shot(june["start_time"]) is True

    reloaded = await _loaded_store(hass)
    assert [s["shot_id"] for s in reloaded.list_shots()] == [july["start_time"]]
    shots = await reloaded.async_get_shots([july["start_time"], june["start_time"]])
    assert [s["shot_id"] for s in shots] == [july["start_time"]]


async def test_files_live_in_domain_folder(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """The files live in the integration's storage folder."""
    store = await _loaded_store(hass)
    await store.async_add_shot(shot_payload())

    assert f"{XENIA_DOMAIN}/{ENTRY_ID}.shots_index" in hass_storage
    assert f"{XENIA_DOMAIN}/{ENTRY_ID}.shots_2026-07" in hass_storage
    assert not any(k.startswith(f"{XENIA_DOMAIN}.") for k in hass_storage)


async def _seed_flat_layout(
    hass: HomeAssistant, hass_storage: dict[str, Any], *payloads: dict[str, Any]
) -> None:
    """Write the v0.7.0-beta.1 flat file layout for the given shots."""
    store = await _loaded_store(hass)
    for payload in payloads:
        await store.async_add_shot(payload)
    await store.async_set_migrated()
    for key in [k for k in hass_storage if k.startswith(f"{XENIA_DOMAIN}/")]:
        hass_storage[key.replace("/", ".", 1)] = hass_storage.pop(key)


async def test_flat_beta_layout_is_relocated(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Files of the flat layout of an earlier beta are moved into the folder."""
    june = shot_payload("2026-06-15T08:00:00.000+00:00")
    july = shot_payload("2026-07-01T10:00:00.000+00:00")
    await _seed_flat_layout(hass, hass_storage, june, july)

    store = await _loaded_store(hass)

    assert [s["shot_id"] for s in store.list_shots()] == [
        july["start_time"],
        june["start_time"],
    ]
    shots = await store.async_get_shots([june["start_time"]])
    assert shots == [{**june, "shot_id": june["start_time"]}]
    # the recorder import must not run a second time
    assert store.migrated is True

    assert not any(k.startswith(f"{XENIA_DOMAIN}.") for k in hass_storage)
    assert f"{XENIA_DOMAIN}/{ENTRY_ID}.shots_index" in hass_storage
    assert f"{XENIA_DOMAIN}/{ENTRY_ID}.shots_2026-06" in hass_storage
    assert f"{XENIA_DOMAIN}/{ENTRY_ID}.shots_2026-07" in hass_storage


async def test_relocation_rerun_keeps_moved_chunks(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """A crash between chunk move and index save must not lose payloads."""
    payload = shot_payload()
    await _seed_flat_layout(hass, hass_storage, payload)
    month = payload["start_time"][:7]
    hass_storage[f"{XENIA_DOMAIN}/{ENTRY_ID}.shots_{month}"] = hass_storage.pop(
        f"{XENIA_DOMAIN}.{ENTRY_ID}.shots_{month}"
    )

    store = await _loaded_store(hass)

    shots = await store.async_get_shots([payload["start_time"]])
    assert shots == [{**payload, "shot_id": payload["start_time"]}]
    assert not any(k.startswith(f"{XENIA_DOMAIN}.") for k in hass_storage)


async def test_malformed_flat_index_is_tolerated(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """A flat index of the wrong shape is left alone and the history starts empty."""
    flat_index_key = f"{XENIA_DOMAIN}.{ENTRY_ID}.shots_index"
    hass_storage[flat_index_key] = {"version": 1, "data": {"bogus": 1}}

    store = await _loaded_store(hass)

    assert store.list_shots() == []
    assert flat_index_key in hass_storage

    payload = shot_payload()
    await store.async_add_shot(payload)
    assert [s["shot_id"] for s in store.list_shots()] == [payload["start_time"]]
    assert f"{XENIA_DOMAIN}/{ENTRY_ID}.shots_index" in hass_storage


async def test_unreadable_flat_chunk_aborts_relocation_until_readable(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """An unreadable flat file stops the move, losing nothing, until it can be read."""
    june = shot_payload("2026-06-15T08:00:00.000+00:00")
    july = shot_payload("2026-07-01T10:00:00.000+00:00")
    await _seed_flat_layout(hass, hass_storage, june, july)
    flat_june_key = f"{XENIA_DOMAIN}.{ENTRY_ID}.shots_2026-06"

    real_load = Store.async_load

    async def load(self):
        if self.key == flat_june_key:
            raise HomeAssistantError("unreadable")
        return await real_load(self)

    with patch.object(Store, "async_load", load):
        store = await _loaded_store(hass)

    # nothing is lost: the unreadable file and the flat index stay in place
    assert store.list_shots() == []
    assert flat_june_key in hass_storage
    assert f"{XENIA_DOMAIN}.{ENTRY_ID}.shots_index" in hass_storage
    assert f"{XENIA_DOMAIN}/{ENTRY_ID}.shots_index" not in hass_storage

    # the next start with a readable file completes the relocation
    store = await _loaded_store(hass)
    shots = await store.async_get_shots([june["start_time"], july["start_time"]])
    assert [s["shot_id"] for s in shots] == [june["start_time"], july["start_time"]]
    assert not any(k.startswith(f"{XENIA_DOMAIN}.") for k in hass_storage)
