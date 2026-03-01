# Testing

The test suite lives in `tests/` and uses `pytest`. All network calls are mocked — no real machine is required to run the tests.

## Running tests

```bash
# Run all tests
uv run pytest tests/

# Run with coverage report
uv run pytest tests/ --cov=custom_components.xenia_home --cov-report=term-missing

# Run a single test file
uv run pytest tests/test_xenia.py

# Run a single test by name
uv run pytest tests/test_xenia.py::test_get_overview_success
```

## Test structure

| File | What it tests |
|---|---|
| `conftest.py` | Shared fixtures and API response payloads |
| `test_xenia.py` | `Xenia` API client methods |
| `test_coordinator.py` | `XeniaDataUpdateCoordinator` and `XeniaConfigCoordinator` |
| `test_config_flow.py` | Config flow — happy path and all error cases |
| `test_init.py` | Integration setup, teardown, and `execute_script` service |
| `test_sensor.py` | Sensor entity values and state |
| `test_binary_sensor.py` | Binary sensor (water tank empty) |
| `test_number.py` | Number entities (set temperature) |
| `test_select.py` | Select entities (power on behavior, script, switch config) |
| `test_switch.py` | Switch entities (power, eco, steam boiler) |
| `test_button.py` | Execute script button |
| `test_event.py` | Shot tracker event entity |

## Writing tests

### Shared fixtures

`conftest.py` provides ready-made fixtures you can inject into any test:

```python
def test_example(overview_data, overview_single_data, config_data, mock_session):
    ...
```

| Fixture | Type | Description |
|---|---|---|
| `overview_data` | `XeniaOverviewData` | Parsed overview API response |
| `overview_single_data` | `XeniaOverviewSingleData` | Parsed overview_single API response |
| `machine_data` | `XeniaMachineData` | Parsed machine API response |
| `coordinator_data` | `XeniaCoordinatorData` | Combined fast coordinator data |
| `config_data` | `XeniaConfigData` | Combined config coordinator data |
| `mock_session` | `MagicMock` | Fake `aiohttp.ClientSession` |

The raw API payload dicts (`OVERVIEW_PAYLOAD`, `MACHINE_PAYLOAD`, etc.) are also importable from `conftest.py` for tests that need to modify specific fields.

### Mocking HTTP calls

All HTTP responses are mocked via `unittest.mock`. Use `AsyncMock` for async context managers:

```python
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.mark.asyncio
async def test_get_overview_success(mock_session):
    mock_resp = AsyncMock()
    mock_resp.json = AsyncMock(return_value={"MA_STATUS": 1, ...})
    mock_resp.raise_for_status = MagicMock()
    mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_session.get.return_value.__aexit__ = AsyncMock(return_value=False)

    xenia = Xenia("192.168.1.1", mock_session)
    data = await xenia.get_overview()

    assert data.ma_status == MachineStatus.ON
```

### Mocking coordinators

For entity tests, build a coordinator with pre-populated data using `MagicMock`:

```python
from unittest.mock import MagicMock

def make_coordinator(coordinator_data, config_data):
    config_entry = MagicMock()
    config_entry.data = {"host": "192.168.1.1"}
    config_entry.options = {}
    config_entry.runtime_data.config_coordinator.data = config_data

    coordinator = MagicMock()
    coordinator.data = coordinator_data
    coordinator.config_entry = config_entry
    coordinator.xenia = MagicMock()
    return coordinator
```

### Testing error paths

Always test what happens when the API fails:

```python
@pytest.mark.asyncio
async def test_get_overview_raises_on_http_error(mock_session):
    mock_resp = AsyncMock()
    mock_resp.raise_for_status.side_effect = aiohttp.ClientError("timeout")
    mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_session.get.return_value.__aexit__ = AsyncMock(return_value=False)

    xenia = Xenia("192.168.1.1", mock_session)
    with pytest.raises(aiohttp.ClientError):
        await xenia.get_overview()
```

### Testing entity state

```python
def test_sensor_native_value(coordinator_data, config_data):
    coordinator = make_coordinator(coordinator_data, config_data)
    sensor = XeniaSensor(coordinator, SENSOR_TYPES[0])

    assert sensor.native_value == coordinator_data.overview.bg_sens_temp_a
```

### Async tests

Mark async tests with `@pytest.mark.asyncio`:

```python
import pytest

@pytest.mark.asyncio
async def test_async_something():
    result = await some_async_function()
    assert result is not None
```

## Local Home Assistant instance

To manually test the integration against a real machine, run HA in Docker:

```bash
# Create config directory and symlink the integration
mkdir -p config/custom_components
ln -s ../../custom_components/xenia_home config/custom_components/xenia_home

# Start HA (use --network host so the container can reach the machine on your LAN)
docker run -d --name hass-dev \
  --network host \
  -v $(pwd)/config:/config \
  -v $(pwd)/custom_components/xenia_home:/config/custom_components/xenia_home \
  ghcr.io/home-assistant/home-assistant:2026.2
```

HA is then available at `http://localhost:8123`. The integration code is mounted as a volume — after code changes, restart the container:

```bash
docker restart hass-dev
```

Enable debug logging by adding this to `config/configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.xenia_home: debug
```

To stop and remove the container:

```bash
docker stop hass-dev && docker rm hass-dev
```

## Coverage

Target coverage is 90%+. The following areas are excluded because they require the full Home Assistant test harness:

- `async_setup_entry` function bodies in platform files (lines 13–20 range)
- `device_info` and `runtime_data` property bodies in `entity.py`
- Platform registration loop in `__init__.py`

To add full integration tests (including these areas), install `pytest-homeassistant-custom-component` and use its `hass` fixture.
