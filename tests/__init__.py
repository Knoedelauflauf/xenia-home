"""Tests for the Xenia espresso machine integration."""

from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xenia_home.const import XENIA_DOMAIN

if TYPE_CHECKING:
    from tests.conftest import MockXeniaApi


async def setup_integration(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up the integration for `entry`."""
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def setup_second_machine(
    hass: HomeAssistant, mock_xenia_api: MockXeniaApi
) -> tuple[MockConfigEntry, MockXeniaApi]:
    """Set up a second machine on xenia2.local; return its entry and machine."""
    machine = mock_xenia_api.for_host("xenia2.local")
    machine.set_overview_single(MA_MAC="AA:BB:CC:DD:EE:01")
    entry = MockConfigEntry(
        domain=XENIA_DOMAIN,
        title="xenia2.local",
        unique_id="aa:bb:cc:dd:ee:01",
        minor_version=2,
        data={"host": "xenia2.local"},
    )
    await setup_integration(hass, entry)
    return entry, machine
