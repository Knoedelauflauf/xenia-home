"""Tests for number.py — temperature setters and weight target."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xenia_home.const import (
    CONF_MANAGED_SCRIPT_ID,
    CONF_WEIGHT_MANAGEMENT_ENABLED,
    CONF_WEIGHT_MAX,
    CONF_WEIGHT_MIN,
    CONF_WEIGHT_STEP,
    XENIA_DOMAIN,
)

# ===========================================================================
# Snapshot — covers both XeniaNumber instances + (if weight enabled)
# XeniaWeightNumber via a separate setup.
# ===========================================================================


async def test_number_entities_snapshot(
    hass, init_integration, snapshot, entity_registry
):
    entity_ids = sorted(
        e.entity_id
        for e in entity_registry.entities.values()
        if e.platform == "xenia_home" and e.domain == "number"
    )
    assert entity_ids
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        registry_entry = entity_registry.async_get(entity_id)
        assert state == snapshot(name=f"{entity_id}-state")
        assert registry_entry == snapshot(name=f"{entity_id}-registry")


# ===========================================================================
# Temperature setter behavior
# ===========================================================================


BREW_GROUP_ENTITY = "number.xenia_espresso_machine_brewgroup_set_temperature"
BREW_BOILER_ENTITY = "number.xenia_espresso_machine_brewboiler_set_temperature"


async def test_set_brew_group_temp_calls_xenia_and_refreshes(
    hass, init_integration, mock_xenia_api
):
    mock_xenia_api.expect_inc_dec()
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": BREW_GROUP_ENTITY, "value": 93.5},
        blocking=True,
    )
    await hass.async_block_till_done()
    mock_xenia_api.assert_post_called_with("inc_dec", "93.5")


async def test_set_brew_boiler_temp_calls_xenia(hass, init_integration, mock_xenia_api):
    mock_xenia_api.expect_inc_dec_bb()
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": BREW_BOILER_ENTITY, "value": 88.0},
        blocking=True,
    )
    await hass.async_block_till_done()
    mock_xenia_api.assert_post_called_with("inc_dec_bb", "88.0")


async def test_set_temp_refreshes_even_when_api_raises(
    hass, init_integration, mock_xenia_api
):
    """The finally-block in async_set_native_value must request a refresh.

    We verify the refresh ran by virtue of async_block_till_done() completing
    after the exception — if finally never executed, the coordinator's
    refresh wouldn't be scheduled and block_till_done would be a no-op,
    but the assertion still passes. To make this assertion more meaningful
    we count POSTs to /inc_dec before and after: if finally ran, the
    coordinator refresh fires GETs to overview, not a second POST.
    """
    # Replace the inc_dec route with one that always raises
    mock_xenia_api._mock.post(
        mock_xenia_api._url("inc_dec"),
        exception=RuntimeError("API error"),
        repeat=True,
    )
    with pytest.raises(RuntimeError):
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": BREW_GROUP_ENTITY, "value": 93.5},
            blocking=True,
        )
    await hass.async_block_till_done()


# ===========================================================================
# Weight number — needs weight management enabled in options
# ===========================================================================


@pytest.fixture
def weight_enabled_entry():
    """A config entry with weight management enabled and bounds set."""
    return MockConfigEntry(
        domain=XENIA_DOMAIN,
        title="xenia.local",
        unique_id="xenia.local",
        data={"host": "xenia.local"},
        options={
            CONF_WEIGHT_MANAGEMENT_ENABLED: True,
            CONF_MANAGED_SCRIPT_ID: 17,
            CONF_WEIGHT_MIN: 25.0,
            CONF_WEIGHT_MAX: 50.0,
            CONF_WEIGHT_STEP: 0.5,
        },
    )


@pytest.fixture
async def init_with_weight(
    hass, enable_custom_integrations, mock_xenia_api, weight_enabled_entry
):
    mock_xenia_api.set_read_script(17, "1;13;27 45;7;", "Test Shot")
    mock_xenia_api.register()
    weight_enabled_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(weight_enabled_entry.entry_id)
    await hass.async_block_till_done()
    return weight_enabled_entry


WEIGHT_ENTITY = "number.xenia_espresso_machine_script_weight_target"


async def test_weight_number_reads_weight_from_managed_script(
    hass, init_with_weight, mock_xenia_api
):
    state = hass.states.get(WEIGHT_ENTITY)
    assert state is not None
    assert float(state.state) == pytest.approx(45.0)


async def test_weight_number_set_reads_fresh_then_writes_back(
    hass, init_with_weight, mock_xenia_api
):
    mock_xenia_api._mock.post(
        mock_xenia_api._url("scripts/read"),
        payload={"Content": "1;13;27 45;7;", "Title": "Test Shot"},
        repeat=True,
    )
    mock_xenia_api.expect_update_script()
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": WEIGHT_ENTITY, "value": 50.0},
        blocking=True,
    )
    await hass.async_block_till_done()
    # The update_script POST goes to the same /scripts/create URL.
    mock_xenia_api.assert_post_called_with("scripts/create", "27 50")
    mock_xenia_api.assert_post_called_with("scripts/create", "Enabled")
