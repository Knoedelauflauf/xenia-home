# Agent and developer instructions

Working notes for AI coding assistants (Claude Code, GitHub Copilot, Codex) and human contributors. Generic Home Assistant conventions are not repeated here — see the references at the bottom. Only project-specific information lives in this file.

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
uv run ruff format custom_components/xenia_home/
uv run ruff check custom_components/xenia_home/
uv run mypy custom_components/xenia_home/
```

To run the integration against a real machine for manual testing:

```bash
docker compose up -d                                        # exposes HA at http://localhost:8123
```

## Project-specific architecture

### Dual coordinator pattern

Two `DataUpdateCoordinator` instances are stored in `entry.runtime_data` as `XeniaRuntimeData`:

- **`XeniaDataUpdateCoordinator`** — sub-second to several-second poll interval, switches dynamically based on machine state (`BREWING` / `READY` / `IDLE`). Polls `/api/v2/overview` and `/api/v2/overview_single`.
- **`XeniaConfigCoordinator`** — one-hour interval. Polls `/api/v2/machine`, `/api/v2/scripts/list`, `/api/v2/switches`, and the optionally-configured managed weight script.

In any `XeniaEntity` subclass:

```python
self.coordinator.data                          # XeniaCoordinatorData (live)
self.runtime_data.config_coordinator.data      # XeniaConfigData (slow)
```

### Type-safe config entry access

Both coordinators declare `config_entry: XeniaConfigEntry` as a class attribute, so mypy knows the field is never `None` — no `assert` is needed:

```python
self._attr_unique_id = f"...{coordinator.config_entry.data[CONF_HOST]}"
```

### Device client

`xenia.py` is an inlined async HTTP client. Keeping it in-tree avoids the dependency-transparency burden for an API only this integration speaks. All HTTP calls use `ClientTimeout(total=N)` (never a bare `int`).

## Project-specific test fixtures

| Fixture | Purpose |
|---|---|
| `mock_xenia_api` | Wrapper around `aioresponses`. Setters (`set_overview`, `set_scripts`, ...) before integration setup; `expect_*` and `assert_post_called_with` after. |
| `mock_config_entry` | A `MockConfigEntry` for the xenia domain with default options. |
| `mock_config_entry_factory_with_options` | Factory for building a `MockConfigEntry` with custom options preloaded. |
| `init_integration` | Wires `mock_xenia_api` + `mock_config_entry` together and calls `async_setup_entry`. Returns the loaded entry. |

Pure-logic tests (`test_xenia.py`, `test_script_parser.py`, `test_coordinator.py`) do not need the `hass` fixture and run in milliseconds. All other test files use `pytest-homeassistant-custom-component`'s `hass` fixture.

`xfail` markers are printed in the pytest session summary so deferred bugs stay visible.

## References

- **Home Assistant developer docs:** <https://developers.home-assistant.io/> — architecture, coding standards, entity patterns, error-handling, async rules. All generic conventions live there.
- **Quality scale rules:** <https://developers.home-assistant.io/docs/core/integration-quality-scale/> — Bronze through Platinum, with the exact text of every rule.
- **`quality-scale-rule-verifier` agent:** defined at `.claude/agents/quality-scale-rule-verifier.md` in the Home Assistant Core repository (<https://github.com/home-assistant/core>). In a Claude Code session with that repository on disk, dispatch the agent against this integration to verify a specific rule against its official documentation.
- **Local compliance state:** `QUALITY_SCALE.md` in this repo — a checklist where boxes are only checked once a rule has been verified.
