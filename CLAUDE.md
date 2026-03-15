# Claude Code Instructions - Xenia Espresso Machine Integration

This is a custom Home Assistant integration for Xenia Espresso Machines. These instructions help ensure code quality and consistency.

## Project Overview

- **Domain**: `xenia_home`
- **Integration Type**: Device (local polling)
- **IoT Class**: Local polling
- **Platforms**: sensor, binary_sensor, number, select, switch, button, event
- **Codeowners**: @knoedelauflauf

## Python Requirements

- **Compatibility**: Python 3.13+
- **Language Features**: Use the newest features when possible:
  - Pattern matching
  - Type hints
  - f-strings (preferred over `%` or `.format()`)
  - Dataclasses
  - Walrus operator

## Code Quality Standards

- **Formatting**: Ruff
- **Linting**: Ruff
- **Type Checking**: MyPy
- **Testing**: pytest with plain functions and fixtures
- **Language**: American English for all code, comments, and documentation (use sentence case, including titles)

### Writing Style Guidelines
- **Tone**: Friendly and informative
- **Perspective**: Use second-person ("you" and "your") for user-facing messages
- **Clarity**: Write for non-native English speakers
- **Formatting in Messages**:
  - Use backticks for: file paths, filenames, variable names, field entries
  - Use sentence case for titles and messages
  - Avoid abbreviations when possible

## Code Organization

### File Structure
```
custom_components/xenia_home/
├── __init__.py          # Entry point with async_setup_entry
├── manifest.json        # Integration metadata
├── const.py            # Domain and constants
├── config_flow.py      # UI configuration and options flow
├── coordinator.py      # Data update coordinators (fast + config)
├── entity.py          # Base entity class and shared helpers
├── xenia.py           # Device API client
├── script_parser.py   # Script instruction parser
├── sensor.py          # Sensor platform
├── binary_sensor.py   # Binary sensor platform
├── number.py          # Number platform (temperatures + weight target)
├── select.py          # Select platform
├── switch.py          # Switch platform
├── button.py          # Button platform (script execution)
├── event.py           # Event platform (shot tracking)
├── strings.json       # User-facing text and translations
└── services.yaml      # Service definitions
```

### Key Modules
- **xenia.py**: Device communication logic (HTTP API client)
- **coordinator.py**: Dual coordinator pattern — fast (1s) and config (1h)
- **entity.py**: Base entity definitions and shared `build_device_info()` helper
- **config_flow.py**: Configuration flow for UI-based setup and options flow for weight management
- **script_parser.py**: Pure Python parser for machine script instructions

### Runtime Data Storage
Use `ConfigEntry.runtime_data` to store both coordinators:
```python
type XeniaConfigEntry = ConfigEntry[XeniaRuntimeData]

async def async_setup_entry(hass: HomeAssistant, entry: XeniaConfigEntry) -> bool:
    coordinator = XeniaDataUpdateCoordinator(hass, entry, xenia)
    config_coordinator = XeniaConfigCoordinator(hass, entry, xenia)
    await coordinator.async_config_entry_first_refresh()
    await config_coordinator.async_config_entry_first_refresh()
    entry.runtime_data = XeniaRuntimeData(coordinator, config_coordinator)
```

## Async Programming

- All external I/O operations must be async
- **Best Practices**:
  - Avoid sleeping in loops
  - Avoid awaiting in loops - use `gather` instead
  - No blocking calls
  - Use `async_get_clientsession(hass)` for HTTP requests

### Data Update Coordinators
The integration uses two coordinators:
- **`XeniaDataUpdateCoordinator`** — polls every 1 second for live sensor data
- **`XeniaConfigCoordinator`** — polls every 1 hour for config data (scripts, switches, firmware, managed script)

```python
async def _async_update_data(self):
    try:
        data = await self.xenia.get_overview()
    except (ClientError, OSError, TimeoutError) as err:
        raise UpdateFailed(f"Xenia fetch failed: {err}") from err
    return data
```

## Configuration Flow

- **UI Setup Required**: Integration supports configuration via UI
- **Data Storage**:
  - Connection-critical config: Store in `ConfigEntry.data`
  - Non-critical settings: Store in `ConfigEntry.options`
- **Validation**: Always validate user input before creating entries
- **Connection Testing**: Test device connection during config flow
- **Duplicate Prevention**: Prevent duplicate configurations using unique IDs

## Entity Development

### Unique IDs
Every entity must have a unique ID for registry tracking:
```python
class XeniaSensor(CoordinatorEntity):
    def __init__(self, coordinator: XeniaDataUpdateCoordinator, device_id: str, sensor_type: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{device_id}_{sensor_type}"
```

### Entity Naming
Use `has_entity_name` pattern:
```python
class XeniaSensor(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: XeniaDataUpdateCoordinator, description) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_device_info = DeviceInfo(
            identifiers={(XENIA_DOMAIN, coordinator.device_id)},
            name="Xenia Espresso Machine",
            manufacturer="Xenia",
        )
```

### State Handling
- Unknown values: Use `None` (not "unknown" or "unavailable")
- Availability: Implement `available()` property

## Error Handling

- **Exception Types**: Choose most specific exception available
  - `ServiceValidationError`: User input errors
  - `HomeAssistantError`: Device communication failures
  - `ConfigEntryNotReady`: Temporary setup issues (device offline)
  - `ConfigEntryAuthFailed`: Authentication problems
  - `UpdateFailed`: Coordinator update failures

### Try/Catch Best Practices
- Only wrap code that can throw exceptions
- Keep try blocks minimal - process data after the try/catch
- **Avoid bare exceptions** except in config flows and background tasks

Good pattern:
```python
try:
    data = await self.client.get_data()  # Can throw
except ClientError as err:
    raise UpdateFailed(f"Failed to fetch data: {err}") from err

# Process data outside try block
temperature = data.get("temperature")
self._attr_native_value = temperature
```

## Logging

- **Format Guidelines**:
  - No periods at end of messages
  - No integration names/domains (added automatically)
  - No sensitive data (keys, tokens, passwords)
- Use debug level for non-user-facing messages
- **Use Lazy Logging**:
  ```python
  _LOGGER.debug("Processing data for %s", device_id)
  ```

## Service Actions

- **Registration**: Register service actions in `async_setup`
- **Validation**: Check config entry existence and loaded state
- **Exception Handling**: Raise appropriate exceptions:
  ```python
  # For invalid input
  if end_date < start_date:
      raise ServiceValidationError("End date must be after start date")

  # For service errors
  try:
      await client.perform_action()
  except ClientError as err:
      raise HomeAssistantError("Could not connect to device") from err
  ```

## Testing

- **Location**: Create tests in the integration's test directory
- **Coverage**: Aim for high test coverage
- **Best Practices**:
  - Use pytest fixtures
  - Mock all external dependencies (network calls, device API)
  - Use snapshots for complex data structures
  - Test all config flow paths

### Running Tests
```bash
# Run tests for this integration
uv run pytest tests/

# With coverage
uv run pytest tests/ --cov=custom_components.xenia_home --cov-report=term-missing
```

## Development Commands

### Code Quality & Linting
```bash
# Run ruff formatting
uv run ruff format custom_components/xenia_home/

# Run ruff linting
uv run ruff check custom_components/xenia_home/

# Run MyPy type checking
uv run mypy custom_components/xenia_home/
```

## Common Anti-Patterns to Avoid

### ❌ **Avoid These Patterns**
```python
# Blocking operations in event loop
data = requests.get(url)  # ❌ Blocks event loop
time.sleep(5)  # ❌ Blocks event loop

# Hardcoded strings
self._attr_name = "Temperature Sensor"  # ❌ Not translatable

# Missing error handling
data = await self.api.get_data()  # ❌ No exception handling

# Too much code in try block
try:
    response = await client.get_data()
    temperature = response["temperature"] / 10  # ❌ Should be outside try
    self._attr_native_value = temperature
except ClientError:
    _LOGGER.error("Failed")
```

### ✅ **Use These Patterns Instead**
```python
# Async operations
data = await hass.async_add_executor_job(requests.get, url)
await asyncio.sleep(5)  # ✅ Non-blocking

# Translatable entity names
_attr_translation_key = "temperature"  # ✅ With strings.json entry

# Proper error handling
try:
    data = await self.api.get_data()
except ApiException as err:
    raise UpdateFailed(f"API error: {err}") from err

# Process outside try block
temperature = data.get("temperature", 0) / 10
self._attr_native_value = temperature
```

## Documentation Standards

- **File Headers**: Short and concise
  ```python
  """Integration for Xenia Espresso Machines."""
  ```
- **Method/Function Docstrings**: Required for all public methods
  ```python
  async def async_setup_entry(hass: HomeAssistant, entry: XeniaConfigEntry) -> bool:
      """Set up Xenia from a config entry."""
  ```
- **Comment Style**: Explain the "why" not just the "what"

## Git Commit Practices

- **NEVER amend, squash, or rebase commits after review has started**
- Reviewers need to see what changed since their last review
- Create clear, descriptive commit messages
- Include Co-Authored-By line when appropriate

## Home Assistant Integration Guidelines

This integration follows Home Assistant's integration patterns:
- Config flow for UI-based setup
- Update coordinator for efficient data fetching
- Device registry for device management
- Entity registry for entity tracking
- Proper async/await patterns
- Type hints throughout
- Comprehensive error handling

For more details on Home Assistant development, see the official developer documentation.
