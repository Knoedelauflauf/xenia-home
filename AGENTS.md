# Agent and developer instructions

Working notes for AI coding assistants (Claude Code, GitHub Copilot, Codex) and human contributors. Generic Home Assistant conventions are not repeated here; see the references at the bottom. Only project-specific information lives in this file.

## Project context

- **Domain**: `xenia_home`
- **Integration type**: device, local polling, HTTP API v2
- **Python version**: matches `pyproject.toml` (`requires-python`)
- **End-user docs**: see `README.md`
- **Quality scale compliance**: see `QUALITY_SCALE.md`

## Development setup

```bash
uv sync                                                     # install dev deps
uv run pytest                                               # all tests
uv run pytest tests/test_sensor.py::test_x -v               # single test
uv run pytest tests/ --snapshot-update                      # after intentional snapshot changes
uv run pytest tests/ --cov=custom_components.xenia_home     # with coverage
uv run ruff format .
uv run ruff check .                                         # tests/ruff.toml relaxes rules for tests, as in core
uv run mypy custom_components/xenia_home/
```

mypy uses the global and the strict per-integration settings of Home Assistant Core (`pyproject.toml`). `XeniaEntity.async_entity_id_changed` in `entity.py` carries `type: ignore[misc,unused-ignore]` because the hook only exists from Home Assistant 2026.11 on; the ignores let mypy pass on both versions. Drop them once the minimum is 2026.11.

CI runs these checks with `uv sync --locked` and `pytest --cov`, so coverage below `fail_under` fails the build (`.github/workflows/test.yml`). `.github/workflows/validate.yml` runs hassfest and the HACS action on every push, pull request and weekly.

To run the integration against a real machine for manual testing:

```bash
docker compose up -d                                        # exposes HA at http://localhost:8123
```

### Optional: pylint with the Home Assistant Core plugin

The ruff config in `pyproject.toml` is copied from home-assistant/core, but Home Assistant Core also maintains a pylint plugin (`pylint_home_assistant`) that runs HA-specific checks ruff cannot express: `enforce_runtime_data`, `exception_translations`, `logger`, `mdi_icons`, `enforce_super_call`, action/config-flow checks, and more. The plugin is not on PyPI; it lives in the HA Core repo.

A `[tool.pylint.*]` section in `pyproject.toml` is set up to load that plugin when a local HA Core checkout is available; it finds the plugin in both the old (`pylint/plugins`) and the current (`packages/pylint-home-assistant`) location. Point `HA_CORE` at it and run:

```bash
HA_CORE=/path/to/home-assistant/core \
  uv run --with "pylint>=4" pylint custom_components/xenia_home/
```

Optional only; ruff and mypy are the canonical local checks.

## Project-specific architecture

### Coordinators

Three coordinators, all `XeniaCoordinator` subclasses, are stored in `entry.runtime_data` as `XeniaRuntimeData`:

- **`XeniaDataUpdateCoordinator`**: polls `/api/v2/overview` every second while the machine is on, brewing or draining, and every five seconds otherwise (`POLL_INTERVAL_*` in `const.py`). After a command, `async_write` has a coordinator poll again one second later (`COMMAND_REFRESH_DELAY`), since the machine reports the new state only then: the config coordinator for switch assignments and the weight target, the overview_single coordinator for setpoints, the live coordinator for everything else.
- **`XeniaOverviewSingleCoordinator`**: polls `/api/v2/overview_single` (setpoints, water tank level) every ten seconds (`POLL_INTERVAL_OVERVIEW_SINGLE`).
- **`XeniaConfigCoordinator`**: polls `/api/v2/machine`, `/api/v2/scripts/list`, `/api/v2/switches` and the optionally configured managed weight script every hour.

`XeniaEntity` is bound to the coordinator that holds its data, the live one unless given another (`XeniaEntity[XeniaOverviewSingleCoordinator]` for the water tank and the setpoints), and also listens to the config coordinator; its availability follows its own coordinator. An update of the config coordinator only rewrites the entity state; logic that runs per live sample, like the shot tracker in `event.py`, must stay in `_handle_coordinator_update` of an entity bound to the live coordinator.

In any `XeniaEntity` subclass:

```python
self.coordinator.data  # XeniaCoordinatorData (live) or XeniaOverviewSingleData
self.runtime_data.config_coordinator.data  # XeniaConfigData (slow)
```

### Stable unique ids

Device identifiers and entity unique ids are keyed on `machine_id(entry)`, the config entry's unique id: the formatted `MA_MAC` of `/api/v2/overview_single`. Every firmware reports it, unlike `MA_SN`. The user step updates the host of an entry whose machine is added again; the reconfigure step aborts with `unique_id_mismatch` for another machine. Entity unique ids are `{machine_id}_{key}`, without the domain (quality scale rule `entity-unique-id`). Never build ids from `entry.data[CONF_HOST]`.

Entries before config entry version 1.2 have ids built from the host in `entry.data[CONF_HOST]` at the time each entity was created; after a host change in those releases, the entities of the earlier host were left behind. `migration.async_migrate_to_mac` rewrites the ids that hold the current host to `{mac}_{key}`, dropping the `xenia_home_` prefix some of them had, as well as the matching device identifier and the entry's unique id in place, so device ids and entity ids stay; ids of an earlier host are left untouched. `async_migrate_entry` raises `ConfigEntryNotReady` while the machine is offline and `ConfigEntryError` when another entry already has that MAC. Reconfiguring such an entry, or a DHCP request that moves it to a new IP address, runs the migration before it replaces the host, and aborts with `already_configured` when the new host is a machine set up already.

```python
self._attr_unique_id = f"{self.machine_id}_{description.key}"
```

### Device client

`xenia.py` is an inlined async HTTP client. Keeping it in-tree avoids the dependency-transparency burden for an API only this integration speaks. All HTTP calls use `ClientTimeout(total=N)` (never a bare `int`). The machine answers one request at a time, so every request of a loaded entry holds its client's `asyncio.Lock`, the options flow included; only the config flow's single MAC lookup uses a client of its own. The coordinators poll on their own timers, and a live poll waits for the requests queued before it. `test_requests_to_the_machine_never_overlap` in `tests/test_coordinator.py` holds this.

## Project-specific test fixtures

| Fixture | Purpose |
|---|---|
| `mock_xenia_api` | Autouse fake machine on `xenia.local`, built on `aioclient_mock`, answering like firmware 4.255; `use_old_firmware` switches to firmware before 4.159. Setters (`set_overview`, `set_scripts`, `set_script`, ...) change the answers at any time; write endpoints accept every request, an unknown script reads as empty fields and an unknown path redirects, as on the machine. `override`, `fail` and `restore` change single endpoints, `answer_slowly` lets the requests to a path take frozen time, during which another request counts as overlapping in `max_in_flight`, the most requests in flight at once. `bodies` and `times` return the bodies and arrival times of the requests. `for_host` adds a second machine. |
| `mock_config_entry` | A `MockConfigEntry` for `xenia.local` without options. |
| `mock_config_entry_factory_with_options` | Factory for a `MockConfigEntry` with the given options. |
| `init_integration` | Sets up `mock_config_entry` and returns it. |
| `poll` | Serves an overview and lets one second pass, so the live coordinator polls once while the machine is on. |

`tests/__init__.py` holds `setup_integration`, `setup_second_machine`, `pass_seconds`, `run_for` (lets time pass in 10 ms steps, running each timer when due), `ws_command`, `listed_shots` and `stored_shots` (shot history files in the format 0.7.0 wrote). Tests drive the machine through `mock_xenia_api` and time through `poll`, `pass_seconds`, `run_for` or `freezer`, and assert on states, registries, actions, events and the websocket API; they do not reach into coordinators, entities or `runtime_data`. A test for behaviour faster than a poll interval waits less than that interval, so the regular poll cannot hide a missing early path. Documented names (action fields, option keys, select options, API status values) are written out in tests rather than imported, so renaming one fails a test.

## References

- **Home Assistant developer docs:** <https://developers.home-assistant.io/>: architecture, coding standards, entity patterns, error-handling, async rules. All generic conventions live there.
- **Quality scale rules:** <https://developers.home-assistant.io/docs/core/integration-quality-scale/>: Bronze through Platinum, with the exact text of every rule.
- **`quality-scale-rule-verifier` agent:** defined at `.claude/agents/quality-scale-rule-verifier.md` in the Home Assistant Core repository (<https://github.com/home-assistant/core>). In a Claude Code session with that repository on disk, dispatch the agent against this integration to verify a specific rule against its official documentation.
- **Local compliance state:** `QUALITY_SCALE.md` in this repo, a checklist where boxes are only checked once a rule has been verified.
