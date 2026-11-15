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

### Dual coordinator pattern

Two `DataUpdateCoordinator` instances are stored in `entry.runtime_data` as `XeniaRuntimeData`:

- **`XeniaDataUpdateCoordinator`**: polls `/api/v2/overview` and `/api/v2/overview_single` every second while the machine is on, brewing or draining, and every five seconds otherwise (`POLL_INTERVAL_*` in `const.py`).
- **`XeniaConfigCoordinator`**: polls `/api/v2/machine`, `/api/v2/scripts/list`, `/api/v2/switches` and the optionally configured managed weight script every hour.

`XeniaEntity` listens to both. An update of the config coordinator only rewrites the entity state; logic that runs per live sample, like the shot tracker in `event.py`, must stay in `_handle_coordinator_update`, which only the live coordinator calls.

In any `XeniaEntity` subclass:

```python
self.coordinator.data  # XeniaCoordinatorData (live)
self.runtime_data.config_coordinator.data  # XeniaConfigData (slow)
```

### Stable unique ids

Device identifiers and entity unique ids are keyed on `machine_id(entry)`, the config entry's unique id: the formatted `MA_MAC` of `/api/v2/overview_single`. Every firmware reports it, unlike `MA_SN`. The user step updates the host of an entry whose machine is added again; the reconfigure step aborts with `unique_id_mismatch` for another machine. Never build ids from `entry.data[CONF_HOST]`.

Entries before config entry version 1.2 were keyed on their host. `async_migrate_entry` reads the MAC and rewrites the entry's unique id, the device identifier and the entity unique ids in place, so device ids and entity ids stay. It raises `ConfigEntryNotReady` while the machine is offline and `ConfigEntryError` when another entry already has that MAC. Reconfiguring such an entry skips the mismatch check, since its reload migrates it.

```python
self._attr_unique_id = f"{self.machine_id}_{description.key}"
```

### Device client

`xenia.py` is an inlined async HTTP client. Keeping it in-tree avoids the dependency-transparency burden for an API only this integration speaks. All HTTP calls use `ClientTimeout(total=N)` (never a bare `int`).

## Project-specific test fixtures

| Fixture | Purpose |
|---|---|
| `mock_xenia_api` | Autouse fake machine on `xenia.local`, built on `aioclient_mock`. Setters (`set_overview`, `set_scripts`, `set_script`, ...) change the answers at any time; write endpoints accept every request. `override`, `fail` and `restore` change single endpoints, `bodies` and `assert_post_called_with` inspect the requests. `for_host` adds a second machine. |
| `mock_config_entry` | A `MockConfigEntry` for `xenia.local` without options. |
| `mock_config_entry_factory_with_options` | Factory for a `MockConfigEntry` with the given options. |
| `init_integration` | Sets up `mock_config_entry` and returns it. |
| `poll` | Serves an overview and lets one second pass, so the live coordinator polls once while the machine is on. |

`tests/__init__.py` holds `setup_integration` and `setup_second_machine`. Tests drive the machine through `mock_xenia_api` and time through `poll` or `freezer`, and assert on states, actions, events and the stored shots; they do not reach into coordinators or entities.

## References

- **Home Assistant developer docs:** <https://developers.home-assistant.io/>: architecture, coding standards, entity patterns, error-handling, async rules. All generic conventions live there.
- **Quality scale rules:** <https://developers.home-assistant.io/docs/core/integration-quality-scale/>: Bronze through Platinum, with the exact text of every rule.
- **`quality-scale-rule-verifier` agent:** defined at `.claude/agents/quality-scale-rule-verifier.md` in the Home Assistant Core repository (<https://github.com/home-assistant/core>). In a Claude Code session with that repository on disk, dispatch the agent against this integration to verify a specific rule against its official documentation.
- **Local compliance state:** `QUALITY_SCALE.md` in this repo, a checklist where boxes are only checked once a rule has been verified.
