"""Tests for the Xenia espresso machine integration."""

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xenia_home.const import XENIA_DOMAIN


async def setup_integration(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up the integration for `entry`."""
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def setup_second_machine(hass: HomeAssistant) -> MockConfigEntry:
    """Set up a second machine on xenia2.local and return its entry."""
    entry = MockConfigEntry(
        domain=XENIA_DOMAIN,
        title="xenia2.local",
        unique_id="xenia2.local",
        data={"host": "xenia2.local"},
    )
    await setup_integration(hass, entry)
    return entry
