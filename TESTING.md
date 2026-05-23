# Testing

The test suite lives in `tests/` and uses `pytest` with
`pytest-homeassistant-custom-component`, `aioresponses`, and `syrupy`.
All HTTP calls are mocked — no real machine is required.

## Running tests

```bash
# Run all tests
uv run pytest tests/

# With coverage
uv run pytest tests/ --cov=custom_components.xenia_home --cov-report=term-missing

# Single file or single test
uv run pytest tests/test_xenia.py
uv run pytest tests/test_sensor.py::test_sensor_entities_snapshot

# Update syrupy snapshots after intentional changes
uv run pytest tests/ --snapshot-update

# Show open xfail markers at the end of the run
uv run pytest tests/ --tb=no -q | tail -20
```

## Test architecture

There are two layers:

- **Pure-logic tests** (no `hass` fixture): `test_script_parser.py`,
  `test_xenia.py`, `test_coordinator.py`. These use plain pytest and
  `aioresponses` and run in milliseconds.
- **Integration tests** (with `hass` fixture): all other `test_*.py`. These
  spin up a real Home Assistant instance, register the integration via
  `MockConfigEntry`, and assert against actual entity state. HTTP calls
  to the machine are mocked via `aioresponses`.

## Key fixtures

| Fixture | Purpose |
|---|---|
| `hass` | Real HA test instance (from `pytest-homeassistant-custom-component`). |
| `enable_custom_integrations` | Enables loading of custom integrations. Opt-in; depended on by `init_integration` transitively. Pure-unit tests don't need it. |
| `mock_xenia_api` | Wrapper around `aioresponses`. Use setters (`set_overview`, `set_scripts`, ...) before integration setup; use `expect_*` and `assert_post_called_with` after. |
| `mock_config_entry` | A `MockConfigEntry` for the Xenia domain with default options. |
| `mock_config_entry_factory_with_options` | Factory for building a `MockConfigEntry` with custom options preloaded. |
| `init_integration` | Wires `mock_xenia_api` + `mock_config_entry` together and calls `async_setup_entry`. Returns the loaded `MockConfigEntry`. |
| `entity_registry` | Standard HA entity registry. |
| `snapshot` | syrupy snapshot assertion fixture. |

## Writing a new test

For a behavior test:

```python
async def test_eco_button_calls_machine_set_eco(
    hass, init_integration, mock_xenia_api
):
    mock_xenia_api.expect_machine_control()
    await hass.services.async_call(
        "switch", "turn_on",
        {"entity_id": "switch.xenia_espresso_machine_eco_mode"},
        blocking=True,
    )
    await hass.async_block_till_done()
    mock_xenia_api.assert_post_called_with("machine/control", '"2"')
```

For a snapshot test (one per platform is sufficient):

```python
async def test_my_platform_entities_snapshot(
    hass, init_integration, snapshot, entity_registry
):
    entity_ids = sorted(
        e.entity_id
        for e in entity_registry.entities.values()
        if e.platform == "xenia_home" and e.domain == "my_platform"
    )
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        registry_entry = entity_registry.async_get(entity_id)
        assert state == snapshot(name=f"{entity_id}-state")
        assert registry_entry == snapshot(name=f"{entity_id}-registry")
```

After adding or changing entities, regenerate snapshots:

```bash
uv run pytest tests/ --snapshot-update
```

Review the snapshot diff in your editor before committing.

## Known bugs

Production bugs that cannot be fixed immediately are deferred via
`pytest.mark.xfail(strict=True)` on the corresponding test. The
pytest session summary prints all open xfail markers at the end of
every run so they remain visible.

## Coverage

`fail_under = 90` is enforced via `pyproject.toml`. Run
`uv run pytest tests/ --cov` to see the breakdown.

## Local Home Assistant instance

To manually test the integration against a real machine, use the included
`docker-compose.yml`:

```bash
docker compose up -d
```

HA is then available at `http://localhost:8123`.
