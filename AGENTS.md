# AI Agent Instructions

This repository contains `xenia_home`, a Home Assistant custom integration for Xenia espresso machines that polls the machine's HTTP API v2 on the local network. It follows the conventions of Home Assistant Core; this file only adds what is specific to this project. `README.md` is the user documentation, `QUALITY_SCALE.md` the quality scale state.

## Development Commands

- `uv sync` installs the development dependencies.
- `uv run pytest` runs the tests; add `--snapshot-update` after an intentional snapshot change.
- `uv run ruff format .`, `uv run ruff check .` and `uv run mypy custom_components/xenia_home/` check formatting, linting and types with the settings copied from Core.
- CI in `.github/workflows/` runs the same checks with `uv sync --locked`, plus hassfest and the HACS action. Coverage below `fail_under` fails the build.
- Optional: `HA_CORE=/path/to/core uv run --with "pylint>=4" pylint custom_components/xenia_home/` runs Core's pylint plugin from a local Core checkout.
- `docker compose up -d` starts Home Assistant on http://localhost:8123 for manual tests against a real machine.

## The Machine

- It answers one request at a time and slowly. Every request holds the client's lock; do not add parallel or retried requests, and a failure must not make polling more frequent.
- Device identifiers and entity unique ids are keyed on the machine's MAC address, the config entry's unique id. Never build ids from the host.

## Testing

- Tests drive the fake machine (`mock_xenia_api` in `tests/conftest.py`) and time, and assert on states, registries, actions, events and the websocket API. They do not reach into coordinators, entities or `runtime_data`.
- A test of behaviour faster than a poll interval waits less than that interval, so the regular poll cannot hide a missing early path.
- Documented names (action fields, option keys, select options, API status values) are written out in tests, not imported, so renaming one fails a test.

## References

- Home Assistant developer docs: <https://developers.home-assistant.io/>
- Quality scale rules: <https://developers.home-assistant.io/docs/core/integration-quality-scale/>
- Core's `AGENTS.md` and the skills in `.claude/skills` of <https://github.com/home-assistant/core>, for example `ha-integration-knowledge` and `ha-quality-scale-verify`.
