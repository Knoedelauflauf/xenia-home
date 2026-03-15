# AI agent instructions - Xenia Home integration

This document provides instructions for AI coding assistants (Claude Code, GitHub Copilot, etc.) working on this Home Assistant custom integration.

## Project context

This is a **Home Assistant custom integration** for Xenia espresso machines. It provides real-time monitoring, machine control, shot tracking, and script/switch configuration.

- **Domain**: `xenia_home`
- **Python version**: 3.13+
- **Polling**: Local polling over HTTP (API v2)

For the full development guide, see `CONTRIBUTING.md`. For testing instructions, see `TESTING.md`.

## Architecture

### Dual coordinator pattern

The integration uses two coordinators stored in `entry.runtime_data` (`XeniaRuntimeData`):

- **`XeniaDataUpdateCoordinator`** — 1-second interval, polls `/api/v2/overview` and `/api/v2/overview_single`
- **`XeniaConfigCoordinator`** — 1-hour interval, polls `/api/v2/machine`, `/api/v2/scripts/list`, `/api/v2/switches`

Entities access live data via `self.coordinator.data` and config data via `self.runtime_data.config_coordinator.data`.

### Runtime data access

```python
# In any XeniaEntity subclass:
self.coordinator.data           # XeniaCoordinatorData (fast, live)
self.runtime_data.config_coordinator.data  # XeniaConfigData (slow, config)
```

### Config entry access

Both coordinators declare `config_entry: XeniaConfigEntry` as a class attribute. This tells mypy the field is always typed and never `None`, so **no assert is needed**:

```python
def __init__(self, coordinator: XeniaDataUpdateCoordinator) -> None:
    super().__init__(coordinator)
    self._attr_unique_id = f"...{coordinator.config_entry.data[CONF_HOST]}"
```

## Code review guidelines

**Do NOT comment on:**
- Missing imports — caught by ruff
- Formatting — handled by ruff format automatically

**Do focus on:**
- Async/await correctness (no blocking calls, no `time.sleep()`)
- Correct use of `ClientTimeout(total=N)` for all aiohttp calls
- Proper exception types (`UpdateFailed`, `ConfigEntryNotReady`, `ServiceValidationError`, etc.)
- Entity unique IDs and translation keys
- Type hint accuracy

## Quality checks

All four must pass before merge:

```bash
uv run ruff format custom_components/xenia_home/
uv run ruff check custom_components/xenia_home/
uv run mypy custom_components/xenia_home/
uv run pytest tests/ --cov=custom_components.xenia_home
```

## Common patterns

### Adding a sensor

```python
XeniaSensorEntityDescription(
    key="my_sensor",
    translation_key="my_sensor",      # must exist in strings.json + de.json
    device_class=SensorDeviceClass.TEMPERATURE,
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    value_fn=lambda data: data.overview.some_field,
)
```

### Adding an API method

```python
async def my_method(self) -> dict:
    """Describe what this method does."""
    url = f"http://{self._host}/api/v2/endpoint"
    async with self._session.get(url, timeout=ClientTimeout(total=10)) as resp:
        resp.raise_for_status()
        return await resp.json()
```

### Error handling

```python
# In coordinator
try:
    data = await self.xenia.get_data()
except (ClientError, OSError, TimeoutError) as err:
    raise UpdateFailed(f"Fetch failed: {err}") from err

# In service handler
try:
    await xenia.do_something()
except (ClientError, OSError, TimeoutError) as err:
    raise HomeAssistantError("Could not reach machine") from err
```

### Translations

Every new entity needs an entry in both:
- `custom_components/xenia_home/strings.json`
- `custom_components/xenia_home/translations/de.json`

Use sentence case. Example:
```json
"sensor": {
  "my_sensor": {
    "name": "My sensor"
  }
}
```

## Anti-patterns to avoid

```python
# ❌ Bare int timeout
async with self._session.get(url, timeout=10) as resp: ...

# ✅ Correct
async with self._session.get(url, timeout=ClientTimeout(total=10)) as resp: ...

# ❌ assert to guard config_entry
assert coordinator.config_entry is not None
self._attr_unique_id = f"...{coordinator.config_entry.data[CONF_HOST]}"

# ✅ Correct — no assert needed, coordinators type config_entry as a class attribute
self._attr_unique_id = f"...{coordinator.config_entry.data[CONF_HOST]}"

# ❌ Sleep in coordinator
await asyncio.sleep(0.5)  # blocks event loop on every poll

# ✅ No sleep needed — API response time naturally spaces requests

# ❌ Bare except
except Exception as e: ...

# ✅ Specific exception
except (ClientError, OSError, TimeoutError) as e: ...
```
