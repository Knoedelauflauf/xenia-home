# Contributing to Xenia Home

Thank you for your interest in contributing! This guide explains how to set up your development environment and follow the project's standards.

## Development setup

### Prerequisites

- Python 3.14.2+
- [uv](https://docs.astral.sh/uv/) for dependency management
- A Xenia espresso machine on your local network (for manual testing)

### Install dependencies

```bash
uv sync
```

This creates a `.venv` and installs all dev dependencies defined in `pyproject.toml`. You do not need to activate the virtual environment — use `uv run` to invoke tools directly.

## Project structure

```
custom_components/xenia_home/   # Integration source code
tests/                          # Test suite
icon.png                        # Integration icon (256x256)
icon@2x.png                     # Integration icon (512x512)
icon.svg                        # Icon source file
```

### Key source files

| File | Purpose |
|---|---|
| `xenia.py` | HTTP API client for the machine |
| `coordinator.py` | Two coordinators: fast (1s) and config (1h) |
| `entity.py` | Shared base entity |
| `config_flow.py` | UI setup flow |
| `__init__.py` | Integration setup and service registration |
| `sensor.py`, `binary_sensor.py`, etc. | Platform implementations |

### Coordinator architecture

The integration uses two `DataUpdateCoordinator` instances:

- **`XeniaDataUpdateCoordinator`** — polls `/api/v2/overview` and `/api/v2/overview_single` every second for live sensor data.
- **`XeniaConfigCoordinator`** — polls `/api/v2/machine`, `/api/v2/scripts/list`, and `/api/v2/switches` every hour for configuration data (firmware version, scripts, switch assignments).

Both are stored in `entry.runtime_data` as `XeniaRuntimeData`.

## Code standards

### Formatting and linting

```bash
# Format code
uv run ruff format custom_components/xenia_home/

# Lint
uv run ruff check custom_components/xenia_home/

# Type check
uv run mypy custom_components/xenia_home/
```

All three must pass before a pull request can be merged.

### Python style

- Python 3.14.2+ features encouraged (pattern matching, type aliases, PEP 649 lazy annotations)
- Type hints on all functions and methods
- f-strings preferred over `.format()` or `%`
- Docstrings required on all public methods

### Async rules

- All I/O must be async — never use `requests` or `time.sleep()`
- Use `aiohttp.ClientTimeout` for all HTTP timeouts (not a bare `int`)
- Avoid `asyncio.sleep()` in update loops

### Error handling

Use the most specific exception available:

| Situation | Exception |
|---|---|
| Device offline at setup | `ConfigEntryNotReady` |
| Coordinator update fails | `UpdateFailed` |
| Bad user input in a service | `ServiceValidationError` |
| Device communication failure | `HomeAssistantError` |

Keep `try` blocks minimal — process data after the `except` block.

### Entity guidelines

- Every entity needs a unique `_attr_unique_id`
- Use `_attr_translation_key` instead of hardcoded names
- No `assert` needed for `config_entry` — both coordinators declare `config_entry: XeniaConfigEntry` as a class attribute, so mypy knows it is never `None`
- Use `@dataclass(frozen=True, kw_only=True)` for all entity description dataclasses
- Translations go in `strings.json` (English) and `translations/de.json` (German)

## Adding a new entity

1. Add the entity description to the relevant platform file (e.g., `sensor.py`)
2. Add a `translation_key` entry to `strings.json` and `translations/de.json`
3. Write tests in `tests/test_<platform>.py`
4. Run the full quality check (see below)

## Adding a new API endpoint

1. Add the method to `xenia.py` — use `ClientTimeout(total=N)` for the timeout
2. If it returns config-like data (changes rarely): add it to `XeniaConfigCoordinator._async_update_data`
3. If it returns live data (changes every second): add it to `XeniaDataUpdateCoordinator._async_update_data`
4. Update the corresponding dataclass (`XeniaConfigData` or `XeniaCoordinatorData`)
5. Write tests in `tests/test_xenia.py` and `tests/test_coordinator.py`

## Full quality check

Run this before opening a pull request:

```bash
uv run ruff format custom_components/xenia_home/ && \
uv run ruff check custom_components/xenia_home/ && \
uv run mypy custom_components/xenia_home/ && \
uv run pytest tests/ --cov=custom_components.xenia_home --cov-report=term-missing
```

All checks must pass and coverage should not drop below 90%.

## Translations

All user-facing strings must be added to both files:

- `custom_components/xenia_home/strings.json` — source of truth (English)
- `custom_components/xenia_home/translations/de.json` — German translation

Use sentence case for all labels and messages.

## Pull request checklist

- [ ] All quality checks pass (ruff, mypy, pytest)
- [ ] New entities have translations in both `strings.json` and `de.json`
- [ ] New API methods use `ClientTimeout`
- [ ] No `assert coordinator.config_entry is not None` — use coordinator class attribute typing instead
