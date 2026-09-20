"""Tests for the diagnostics download."""

from collections.abc import Iterator

from aioresponses import aioresponses as AioResponses
import pytest
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)

from tests.conftest import MockXeniaApi


@pytest.fixture
def mock_xenia_api() -> Iterator[MockXeniaApi]:
    """Let hass_client's localhost requests bypass aioresponses."""
    with AioResponses(passthrough=["http://127.0.0.1"]) as mock:
        yield MockXeniaApi(mock)


async def test_diagnostics(hass, hass_client, init_integration, snapshot):
    assert (
        await get_diagnostics_for_config_entry(hass, hass_client, init_integration)
        == snapshot
    )
