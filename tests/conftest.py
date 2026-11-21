"""Fixtures for the Xenia integration tests."""

import asyncio
from collections.abc import Awaitable, Callable, Generator
from http import HTTPStatus
import json
import re
import time
from typing import Any
from unittest.mock import Mock, patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.syrupy import HomeAssistantSnapshotExtension
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)
from syrupy.assertion import SnapshotAssertion
from yarl import URL

from custom_components.xenia_home.const import XENIA_DOMAIN

from tests import pass_seconds, setup_integration
from tests.fixtures.api_responses import (
    MACHINE_PAYLOAD,
    OLD_FW_MACHINE_PAYLOAD,
    OLD_FW_OVERVIEW_PAYLOAD,
    OVERVIEW_PAYLOAD,
    OVERVIEW_SINGLE_PAYLOAD,
    SCRIPTS_PAYLOAD,
    SWITCHES_PAYLOAD,
)

DEFAULT_HOST = "xenia.local"
DEFAULT_MAC = "aa:bb:cc:dd:ee:ff"

WRITE_ENDPOINTS = {
    ("get", "scripts/stop"),
    ("post", "inc_dec"),
    ("post", "inc_dec_bb"),
    ("post", "machine/control"),
    ("post", "scale/write"),
    ("post", "scripts/create"),
    ("post", "scripts/execute"),
    ("post", "switches"),
    ("post", "toggle/sb"),
}


@pytest.fixture
def entity_registry_enabled_by_default() -> Generator[None]:
    """Enable the entities that start disabled."""
    with patch(
        "homeassistant.helpers.entity.Entity.entity_registry_enabled_default",
        return_value=True,
    ):
        yield


@pytest.fixture
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Return the snapshot assertion with the Home Assistant extension.

    The plugin fixture of the same name can be shadowed by syrupy's own,
    depending on the order pytest discovers the installed plugins.
    """
    return snapshot.use_extension(HomeAssistantSnapshotExtension)


class XeniaMockResponse(AiohttpClientMockResponse):
    """Mock response with the attributes ClientResponseError is built from."""

    @property
    def request_info(self) -> Mock:
        """Return a stand-in for the request info."""
        return Mock(real_url=self.url)

    @property
    def reason(self) -> str:
        """Return the reason phrase of the status."""
        return HTTPStatus(self.status).phrase


class MockXeniaApi:
    """A fake Xenia machine behind aioclient_mock.

    Responses follow the current payloads, so setters take effect at any
    time, also after the integration is set up. Write endpoints accept
    every request unless `override` replaces them.
    """

    def __init__(
        self, aioclient_mock: AiohttpClientMocker, host: str = DEFAULT_HOST
    ) -> None:
        """Answer every request to the API of `host`."""
        self._aioclient_mock = aioclient_mock
        self._host = host
        self._base: dict[str, dict[str, Any]] = {
            "overview": OVERVIEW_PAYLOAD,
            "machine": MACHINE_PAYLOAD,
        }
        self._payloads: dict[str, dict[str, Any]] = {
            "overview": dict(OVERVIEW_PAYLOAD),
            "overview_single": dict(OVERVIEW_SINGLE_PAYLOAD),
            "machine": dict(MACHINE_PAYLOAD),
            "scripts/list": dict(SCRIPTS_PAYLOAD),
            "switches": dict(SWITCHES_PAYLOAD),
        }
        self._script_files: dict[str, dict[str, str]] = {}
        self._overrides: dict[tuple[str, str], dict[str, Any]] = {}
        self._calls: list[tuple[str, str, str, float]] = []
        self._in_flight = 0
        self.max_in_flight = 0
        self._answer_times: dict[str, tuple[FrozenDateTimeFactory, float]] = {}
        api = re.compile(rf"^http://{re.escape(host)}/api/v2/")
        for method in ("get", "post"):
            aioclient_mock.request(method, api, side_effect=self._respond)

    @property
    def host(self) -> str:
        """Return the host this machine answers on."""
        return self._host

    def for_host(self, host: str) -> MockXeniaApi:
        """Return a second machine on another host."""
        return MockXeniaApi(self._aioclient_mock, host)

    def use_old_firmware(self) -> None:
        """Answer like firmware before 4.159, without scale rate and serial."""
        self._base = {
            "overview": OLD_FW_OVERVIEW_PAYLOAD,
            "machine": OLD_FW_MACHINE_PAYLOAD,
        }
        self.set_overview()
        self.set_machine()

    def set_overview(self, **fields: Any) -> None:
        """Serve the default overview with `fields` replaced."""
        self._payloads["overview"] = {**self._base["overview"], **fields}

    def set_overview_single(self, **fields: Any) -> None:
        """Serve the default overview_single with `fields` replaced."""
        self._payloads["overview_single"] = {**OVERVIEW_SINGLE_PAYLOAD, **fields}

    def set_machine(self, **fields: Any) -> None:
        """Serve the default machine payload with `fields` replaced."""
        self._payloads["machine"] = {**self._base["machine"], **fields}

    def set_scripts(self, scripts: dict[int, str]) -> None:
        """Serve `scripts` as {id: title} from the script list."""
        self._payloads["scripts/list"] = {
            "index_list": list(scripts),
            "title_list": list(scripts.values()),
        }

    def set_switches(self, switches: dict[str, int]) -> None:
        """Serve `switches` as the switch assignments."""
        self._payloads["switches"] = dict(switches)

    def set_script(self, script_id: int, content: str, title: str) -> None:
        """Store a script that scripts/read returns for `script_id`."""
        self._script_files[f"{script_id:03d}"] = {"Content": content, "Title": title}

    def override(
        self,
        method: str,
        path: str,
        *,
        status: HTTPStatus = HTTPStatus.OK,
        json: Any = None,
        text: str | None = None,
        exc: Exception | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Answer `method` `path` with a fixed response from now on."""
        self._overrides[(method, path)] = {
            "status": status,
            "json": json,
            "text": text,
            "exc": exc,
            "headers": headers,
        }

    def restore(self, method: str, path: str) -> None:
        """Answer `method` `path` normally again."""
        del self._overrides[(method, path)]

    def fail(self, method: str, path: str) -> None:
        """Answer `method` `path` with an internal server error from now on."""
        self.override(method, path, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def answer_slowly(
        self, freezer: FrozenDateTimeFactory, path: str, seconds: float
    ) -> None:
        """Let each request to `path` take `seconds` of `freezer` time from now on.

        Time passes for everything else while the machine answers, and a
        request sent meanwhile is in flight at the same time, which
        `max_in_flight` records.
        """
        self._answer_times[path] = (freezer, seconds)

    def bodies(self, method: str, path: str) -> list[str]:
        """Return the bodies of all `method` requests to `path`, oldest first."""
        return [body for m, p, body, _ in self._calls if (m, p) == (method, path)]

    def times(self, method: str, path: str) -> list[float]:
        """Return when the `method` requests to `path` arrived, oldest first."""
        return [sent for m, p, _, sent in self._calls if (m, p) == (method, path)]

    async def _respond(self, method: str, url: URL, data: Any) -> XeniaMockResponse:
        method = method.lower()
        path = url.path.removeprefix("/api/v2/")
        self._calls.append(
            (method, path, "" if data is None else str(data), time.monotonic())
        )
        self._in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self._in_flight)
        try:
            return await self._answer(method, path, url, data)
        finally:
            self._in_flight -= 1

    async def _answer(
        self, method: str, path: str, url: URL, data: Any
    ) -> XeniaMockResponse:
        if path in self._answer_times:
            freezer, seconds = self._answer_times[path]
            # The request leaves at an await, as a real one does.
            await asyncio.sleep(0)
            freezer.tick(seconds)
        if (method, path) in self._overrides:
            return XeniaMockResponse(method, url, **self._overrides[(method, path)])
        if method == "get" and path in self._payloads:
            return XeniaMockResponse(method, url, json=self._payloads[path])
        if (method, path) == ("post", "scripts/read"):
            # The machine answers an unknown or deleted script with empty fields.
            script = self._script_files.get(
                json.loads(data)["FILE_NAME"], {"Content": "", "Title": ""}
            )
            return XeniaMockResponse(method, url, json=script)
        if (method, path) in WRITE_ENDPOINTS:
            return XeniaMockResponse(method, url)
        # The firmware redirects unknown paths to its web UI.
        return XeniaMockResponse(
            method, url, status=HTTPStatus.MOVED_PERMANENTLY, headers={"Location": "/"}
        )


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load the integration from custom_components in every test."""


@pytest.fixture(autouse=True)
def mock_xenia_api(aioclient_mock: AiohttpClientMocker) -> MockXeniaApi:
    """Return the fake Xenia machine on the default host; no test reaches the network."""
    return MockXeniaApi(aioclient_mock)


@pytest.fixture
def mock_config_entry_factory_with_options() -> Callable[
    [dict[str, Any]], MockConfigEntry
]:
    """Return a factory for config entries with the given options."""

    def _build(options: dict[str, Any]) -> MockConfigEntry:
        return MockConfigEntry(
            domain=XENIA_DOMAIN,
            title=DEFAULT_HOST,
            unique_id=DEFAULT_MAC,
            minor_version=2,
            data={"host": DEFAULT_HOST},
            options=options,
        )

    return _build


@pytest.fixture
def mock_config_entry(
    mock_config_entry_factory_with_options: Callable[[dict[str, Any]], MockConfigEntry],
) -> MockConfigEntry:
    """Return a config entry without options."""
    return mock_config_entry_factory_with_options({})


@pytest.fixture
async def init_integration(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> MockConfigEntry:
    """Set up the integration and return its config entry."""
    await setup_integration(hass, mock_config_entry)
    return mock_config_entry


@pytest.fixture
def poll(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    freezer: FrozenDateTimeFactory,
) -> Callable[..., Awaitable[None]]:
    """Return a function that serves an overview and lets the next poll happen.

    The machine is polled every second while it is on.
    """

    async def _poll(**fields: Any) -> None:
        mock_xenia_api.set_overview(**fields)
        await pass_seconds(hass, freezer, 1)

    return _poll
