"""Shared pytest fixtures for the xenia_home integration tests."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest
import yarl
from aioresponses import aioresponses as AioResponses

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xenia_home.const import XENIA_DOMAIN
from tests.fixtures.api_responses import (
    MACHINE_PAYLOAD,
    OVERVIEW_PAYLOAD,
    OVERVIEW_SINGLE_PAYLOAD,
    SCRIPTS_PAYLOAD,
    SWITCHES_PAYLOAD,
)

DEFAULT_HOST = "xenia.local"


# Removed autouse: enable_custom_integrations is now pulled in
# transitively via init_integration so only tests that actually load
# the integration pay for it. Pure-unit tests that mock hass do not
# need it.


class MockXeniaApi:
    """Helper around aioresponses that knows the Xenia URL surface.

    Tests use the setter methods to register canned GET responses and the
    `expect_*` methods to declare and later verify mutating POST calls.
    Everything is keyed off a single host (default: xenia.local).
    """

    def __init__(self, mock: AioResponses, host: str = DEFAULT_HOST) -> None:
        self._mock = mock
        self._host = host
        # Default everything to the canonical payloads. Tests override via
        # setters before init_integration runs.
        self._overview: dict[str, Any] = dict(OVERVIEW_PAYLOAD)
        self._overview_single: dict[str, Any] = dict(OVERVIEW_SINGLE_PAYLOAD)
        self._machine: dict[str, Any] = dict(MACHINE_PAYLOAD)
        self._scripts: dict[str, Any] = dict(SCRIPTS_PAYLOAD)
        self._switches: dict[str, Any] = dict(SWITCHES_PAYLOAD)
        self._read_script_responses: dict[int, dict[str, str]] = {}
        self._registered = False

    @property
    def host(self) -> str:
        return self._host

    def _url(self, path: str) -> str:
        return f"http://{self._host}/api/v2/{path}"

    # ---- setters (must be called before init_integration) ----

    def set_overview(self, **fields: Any) -> None:
        self._overview = {**OVERVIEW_PAYLOAD, **fields}

    def set_overview_single(self, **fields: Any) -> None:
        self._overview_single = {**OVERVIEW_SINGLE_PAYLOAD, **fields}

    def set_machine(self, **fields: Any) -> None:
        self._machine = {**MACHINE_PAYLOAD, **fields}

    def set_scripts(self, scripts: dict[int, str]) -> None:
        self._scripts = {
            "index_list": list(scripts.keys()),
            "title_list": list(scripts.values()),
        }

    def set_switches(self, switches: dict[str, int]) -> None:
        self._switches = dict(switches)

    def set_read_script(self, script_id: int, content: str, title: str) -> None:
        """Register a canned response for POST /scripts/read.

        LIMITATION: aioresponses cannot inspect the POST body, so if multiple
        scripts are registered the responses are served in registration order
        on each call, regardless of which script_id the production code
        requests. For most tests this does not matter because only one
        read_script call happens. Tests that need per-call control should
        register their own callbacks via mock_xenia_api._mock.post(...).
        """
        self._read_script_responses[script_id] = {
            "Content": content,
            "Title": title,
        }

    # ---- registration (called by init_integration) ----

    def register(self, *, repeat: bool = True) -> None:
        """Wire all GET responses into aioresponses.

        `repeat=True` so polling-style endpoints (overview, overview_single)
        keep returning the response on every call.
        """
        if self._registered:
            return
        self._mock.get(
            self._url("overview"),
            payload=self._overview,
            repeat=repeat,
        )
        self._mock.get(
            self._url("overview_single"),
            payload=self._overview_single,
            repeat=repeat,
        )
        self._mock.get(
            self._url("machine"),
            payload=self._machine,
            repeat=repeat,
        )
        self._mock.get(
            self._url("scripts/list"),
            payload=self._scripts,
            repeat=repeat,
        )
        self._mock.get(
            self._url("switches"),
            payload=self._switches,
            repeat=repeat,
        )
        # Default: scripts/read POST returns 404 unless the test registered
        # a specific script id. Tests that need read_script must call
        # set_read_script before init_integration.
        for script_id, response in self._read_script_responses.items():
            self._mock.post(
                self._url("scripts/read"),
                payload=response,
                repeat=repeat,
            )
        self._registered = True

    # ---- mutating-call expectations ----

    def expect_machine_control(self) -> None:
        """Register POST /machine/control to accept any control value.

        Use assert_post_called_with("machine/control", '"<value>"') to verify
        a specific MachineControl int was sent.
        """
        self._mock.post(self._url("machine/control"), status=200, repeat=True)

    def expect_toggle_sb(self) -> None:
        self._mock.post(self._url("toggle_sb"), status=200, repeat=True)

    def expect_inc_dec(self) -> None:
        self._mock.post(self._url("inc_dec"), payload={}, repeat=True)

    def expect_inc_dec_bb(self) -> None:
        self._mock.post(self._url("inc_dec_bb"), payload={}, repeat=True)

    def expect_execute_script(self) -> None:
        self._mock.post(self._url("scripts/execute"), status=200, repeat=True)

    def expect_set_switch(self) -> None:
        # set_switch first does a GET then a POST to /switches
        self._mock.post(self._url("switches"), status=200, repeat=True)

    def expect_create_script(self) -> None:
        self._mock.post(self._url("scripts/create"), status=200, repeat=True)

    def expect_update_script(self) -> None:
        # Same endpoint as create_script (Enabled vs Disabled differentiator)
        self._mock.post(self._url("scripts/create"), status=200, repeat=True)

    # ---- assertions ----

    def assert_post_called_with(self, path: str, substring: str) -> None:
        """Assert that some POST to `path` had `substring` in its body."""
        url = self._url(path)
        calls = [call for call in self._mock.requests.get(("POST", yarl.URL(url)), [])]
        assert calls, f"No POST to {url} was made"
        bodies = [str(call.kwargs.get("data", "")) for call in calls]
        assert any(substring in body for body in bodies), (
            f"None of {len(bodies)} POSTs to {url} contained {substring!r}. "
            f"Bodies: {bodies}"
        )

    def post_count(self, path: str) -> int:
        return len(self._mock.requests.get(("POST", yarl.URL(self._url(path))), []))


@pytest.fixture
def mock_xenia_api() -> Iterator[MockXeniaApi]:
    """Provides a MockXeniaApi backed by aioresponses for one test.

    Use the setters (`set_overview`, `set_scripts`, ...) and the `expect_*`
    methods BEFORE calling `init_integration`. After the integration is set
    up, only `assert_*` and `post_count` are useful.
    """
    with AioResponses() as mock:
        yield MockXeniaApi(mock)


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Build a MockConfigEntry for the Xenia integration."""
    return MockConfigEntry(
        domain=XENIA_DOMAIN,
        title="xenia.local",
        unique_id=DEFAULT_HOST,
        data={"host": DEFAULT_HOST},
        options={},
    )


@pytest.fixture
def mock_config_entry_factory_with_options() -> Callable[[dict], MockConfigEntry]:
    """Factory: build a MockConfigEntry with custom options at construction."""

    def _build(options: dict) -> MockConfigEntry:
        return MockConfigEntry(
            domain=XENIA_DOMAIN,
            title="xenia.local",
            unique_id=DEFAULT_HOST,
            data={"host": DEFAULT_HOST},
            options=options,
        )

    return _build


@pytest.fixture
async def init_integration(
    hass,
    enable_custom_integrations,
    mock_config_entry: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
) -> MockConfigEntry:
    """Register all default API responses, set up the integration, return entry.

    Tests inject this and the integration is fully loaded by the time
    the test body starts running. To customize API responses, inject
    `mock_xenia_api` separately and call its setters BEFORE this fixture
    runs — pytest resolves fixtures in dependency order, but for predictable
    ordering, put `mock_xenia_api` and any setter calls in a separate
    fixture or set them as the first lines of the test body before any
    `await`. See test files for examples.
    """
    mock_xenia_api.register()
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry


# ---------------------------------------------------------------------------
# Pytest hook: visible end-of-run summary of open xfails
# ---------------------------------------------------------------------------


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Print a red banner with all xfail-marked tests at the end of a run."""
    xfailed = terminalreporter.stats.get("xfailed", [])
    if not xfailed:
        return
    terminalreporter.write_sep("=", "Open xfail markers (= known bugs)", red=True)
    for report in xfailed:
        terminalreporter.write_line(f"  XFAIL {report.nodeid}")
        terminalreporter.write_line(f"        {report.wasxfail}")
    terminalreporter.write_line(
        f"\n{len(xfailed)} known bugs are deferred."
    )
