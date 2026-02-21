"""Tests for button.py — XeniaExecuteScriptButton."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.xenia_home.button import XeniaExecuteScriptButton
from custom_components.xenia_home.const import XENIA_DOMAIN
from custom_components.xenia_home.coordinator import XeniaConfigData
from custom_components.xenia_home.xenia import XeniaMachineData


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_coordinator(selected_script_id: int | None = None) -> MagicMock:
    coordinator = MagicMock()
    coordinator.config_entry = MagicMock()
    coordinator.config_entry.data = {"host": "xenia.local"}
    coordinator.xenia = MagicMock()
    coordinator.xenia.execute_script = AsyncMock()

    config_coord = MagicMock()
    config_coord.selected_script_id = selected_script_id
    config_coord.data = XeniaConfigData(
        machine=XeniaMachineData.from_dict({}),
        scripts={1: "Espresso", 10: "MyShot"},
        switches={},
    )

    runtime_data = MagicMock()
    runtime_data.config_coordinator = config_coord
    coordinator.config_entry.runtime_data = runtime_data

    return coordinator


def _make_button(coordinator: MagicMock) -> XeniaExecuteScriptButton:
    with patch(
        "custom_components.xenia_home.entity.XeniaEntity.__init__", return_value=None
    ):
        btn = XeniaExecuteScriptButton.__new__(XeniaExecuteScriptButton)
        btn.coordinator = coordinator
        btn.hass = MagicMock()
        XeniaExecuteScriptButton.__init__(btn, coordinator)
    return btn


# ===========================================================================
# XeniaExecuteScriptButton — attributes
# ===========================================================================


def test_execute_script_button_unique_id_includes_domain_and_host() -> None:
    coord = _make_coordinator()
    btn = _make_button(coord)
    assert XENIA_DOMAIN in btn._attr_unique_id
    assert "xenia.local" in btn._attr_unique_id


def test_execute_script_button_translation_key_is_set() -> None:
    coord = _make_coordinator()
    btn = _make_button(coord)
    assert btn._attr_translation_key == "execute_script"


def test_execute_script_button_icon_is_set() -> None:
    coord = _make_coordinator()
    btn = _make_button(coord)
    assert btn._attr_icon == "mdi:play"


# ===========================================================================
# async_press
# ===========================================================================


@pytest.mark.asyncio
async def test_async_press_executes_selected_script() -> None:
    coord = _make_coordinator(selected_script_id=10)
    btn = _make_button(coord)

    await btn.async_press()

    coord.xenia.execute_script.assert_called_once_with(10)


@pytest.mark.asyncio
async def test_async_press_does_nothing_when_no_script_selected() -> None:
    coord = _make_coordinator(selected_script_id=None)
    btn = _make_button(coord)

    await btn.async_press()

    coord.xenia.execute_script.assert_not_called()


@pytest.mark.asyncio
async def test_async_press_does_nothing_when_script_id_is_zero() -> None:
    """Script ID 0 means 'None' — should not execute."""
    coord = _make_coordinator(selected_script_id=0)
    btn = _make_button(coord)

    await btn.async_press()

    coord.xenia.execute_script.assert_not_called()


@pytest.mark.asyncio
async def test_async_press_does_nothing_when_script_id_is_negative() -> None:
    """Negative IDs are invalid and must not be executed."""
    coord = _make_coordinator(selected_script_id=-1)
    btn = _make_button(coord)

    await btn.async_press()

    coord.xenia.execute_script.assert_not_called()


@pytest.mark.asyncio
async def test_async_press_executes_builtin_script_id_one() -> None:
    coord = _make_coordinator(selected_script_id=1)
    btn = _make_button(coord)

    await btn.async_press()

    coord.xenia.execute_script.assert_called_once_with(1)
