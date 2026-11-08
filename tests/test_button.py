"""Tests for the script buttons."""

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.components.select import (
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_OPTION
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from syrupy.assertion import SnapshotAssertion

from tests.conftest import MockXeniaApi

EXECUTE = "button.xenia_espresso_machine_execute_script"
STOP = "button.xenia_espresso_machine_stop_script"
SCRIPT_SELECT = "select.xenia_espresso_machine_script"


async def _press(hass: HomeAssistant, entity_id: str) -> None:
    await hass.services.async_call(
        BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )


async def _select_script(hass: HomeAssistant, title: str) -> None:
    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: SCRIPT_SELECT, ATTR_OPTION: title},
        blocking=True,
    )


async def test_button_entities_snapshot(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
) -> None:
    """The button states and registry entries match the snapshot."""
    for entity_id in (EXECUTE, STOP):
        assert hass.states.get(entity_id) == snapshot(name=f"{entity_id}-state")
        assert entity_registry.async_get(entity_id) == snapshot(
            name=f"{entity_id}-registry"
        )


@pytest.mark.parametrize(("title", "script_id"), [("MyShot", 10), ("Espresso", 1)])
async def test_execute_runs_the_selected_script(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    title: str,
    script_id: int,
) -> None:
    """The execute button runs the script picked in the script select."""
    await _select_script(hass, title)
    await _press(hass, EXECUTE)
    assert mock_xenia_api.bodies("post", "scripts/execute") == [f'{{"ID":{script_id}}}']


@pytest.mark.parametrize("title", [None, "None"])
async def test_execute_without_script_does_nothing(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    title: str | None,
) -> None:
    """Without a selected script, or with "None", nothing runs."""
    if title is not None:
        await _select_script(hass, title)
    await _press(hass, EXECUTE)
    assert mock_xenia_api.bodies("post", "scripts/execute") == []


async def test_stop_stops_the_script(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_xenia_api: MockXeniaApi
) -> None:
    """The stop button stops the running script."""
    await _press(hass, STOP)
    assert len(mock_xenia_api.bodies("get", "scripts/stop")) == 1


@pytest.mark.parametrize(
    ("entity_id", "method", "path"),
    [(EXECUTE, "post", "scripts/execute"), (STOP, "get", "scripts/stop")],
)
async def test_refused_press_raises_translated_error(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    entity_id: str,
    method: str,
    path: str,
) -> None:
    """A press the machine refuses raises a translated error."""
    await _select_script(hass, "MyShot")
    mock_xenia_api.fail(method, path)
    with pytest.raises(HomeAssistantError) as exc_info:
        await _press(hass, entity_id)
    assert exc_info.value.translation_key == "write_failed"
