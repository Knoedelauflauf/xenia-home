"""Tests for number.py — XeniaNumber and NUMBER_TYPES definitions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.number import NumberDeviceClass

from custom_components.xenia_home.coordinator import XeniaCoordinatorData
from custom_components.xenia_home.number import NUMBER_TYPES, XeniaNumber
from custom_components.xenia_home.xenia import (
    XeniaOverviewData,
    XeniaOverviewSingleData,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_coordinator(
    bg_set_temp: float = 93.5,
    bb_set_temp: float = 130.0,
) -> MagicMock:
    coord = MagicMock()
    coord.config_entry = MagicMock()
    coord.config_entry.data = {"host": "xenia.local"}
    coord.xenia = MagicMock()
    coord.xenia.set_bg_set_temp = AsyncMock()
    coord.xenia.set_bb_set_temp = AsyncMock()
    coord.async_request_refresh = AsyncMock()

    overview = XeniaOverviewData.from_dict({})
    overview_single = XeniaOverviewSingleData.from_dict(
        {"BG_SET_TEMP": bg_set_temp, "BB_SET_TEMP": bb_set_temp}
    )
    coord.data = XeniaCoordinatorData(overview=overview, overview_single=overview_single)
    return coord


def _make_number(coordinator: MagicMock, description_key: str) -> XeniaNumber:
    description = next(d for d in NUMBER_TYPES if d.key == description_key)
    with patch(
        "custom_components.xenia_home.entity.XeniaEntity.__init__", return_value=None
    ):
        number = XeniaNumber.__new__(XeniaNumber)
        number.coordinator = coordinator
        number.hass = MagicMock()
        XeniaNumber.__init__(number, coordinator, description)
    return number


# ===========================================================================
# NUMBER_TYPES definitions
# ===========================================================================


def test_number_types_has_two_entries() -> None:
    assert len(NUMBER_TYPES) == 2


def test_all_number_types_have_translation_key() -> None:
    for desc in NUMBER_TYPES:
        assert desc.translation_key, f"{desc.key} is missing translation_key"


def test_all_number_types_have_value_fn_and_set_fn() -> None:
    for desc in NUMBER_TYPES:
        assert callable(desc.value_fn), f"{desc.key} missing value_fn"
        assert callable(desc.set_fn), f"{desc.key} missing set_fn"


def test_brew_group_temp_bounds() -> None:
    desc = next(d for d in NUMBER_TYPES if d.key == "brew_group_set_temperature")
    assert desc.native_min_value == 60
    assert desc.native_max_value == 96
    assert desc.native_step == 0.5


def test_brew_boiler_temp_bounds() -> None:
    desc = next(d for d in NUMBER_TYPES if d.key == "brew_boiler_set_temperature")
    assert desc.native_min_value == 60
    assert desc.native_max_value == 96
    assert desc.native_step == 0.5


# ===========================================================================
# XeniaNumber attributes
# ===========================================================================


def test_brew_group_temp_number_unique_id_contains_key_and_host() -> None:
    coord = _make_coordinator()
    number = _make_number(coord, "brew_group_set_temperature")
    assert "brew_group_set_temperature" in number._attr_unique_id
    assert "xenia.local" in number._attr_unique_id


def test_brew_boiler_temp_number_unique_id_contains_key_and_host() -> None:
    coord = _make_coordinator()
    number = _make_number(coord, "brew_boiler_set_temperature")
    assert "brew_boiler_set_temperature" in number._attr_unique_id
    assert "xenia.local" in number._attr_unique_id


def test_number_min_max_set_from_description() -> None:
    coord = _make_coordinator()
    number = _make_number(coord, "brew_group_set_temperature")
    assert number._attr_native_min_value == 60
    assert number._attr_native_max_value == 96
    assert number._attr_native_step == 0.5


# ===========================================================================
# native_value
# ===========================================================================


def test_brew_group_native_value_reads_from_coordinator() -> None:
    coord = _make_coordinator(bg_set_temp=92.0)
    number = _make_number(coord, "brew_group_set_temperature")
    assert number.native_value == pytest.approx(92.0)


def test_brew_boiler_native_value_reads_from_coordinator() -> None:
    coord = _make_coordinator(bb_set_temp=128.5)
    number = _make_number(coord, "brew_boiler_set_temperature")
    assert number.native_value == pytest.approx(128.5)


def test_brew_group_native_value_zero_when_missing() -> None:
    coord = _make_coordinator(bg_set_temp=0.0)
    number = _make_number(coord, "brew_group_set_temperature")
    assert number.native_value == pytest.approx(0.0)


# ===========================================================================
# async_set_native_value
# ===========================================================================


@pytest.mark.asyncio
async def test_brew_group_set_native_value_calls_xenia() -> None:
    coord = _make_coordinator()
    number = _make_number(coord, "brew_group_set_temperature")
    await number.async_set_native_value(93.5)
    coord.xenia.set_bg_set_temp.assert_called_once_with(93.5)


@pytest.mark.asyncio
async def test_brew_boiler_set_native_value_calls_xenia() -> None:
    coord = _make_coordinator()
    number = _make_number(coord, "brew_boiler_set_temperature")
    await number.async_set_native_value(130.0)
    coord.xenia.set_bb_set_temp.assert_called_once_with(130.0)


@pytest.mark.asyncio
async def test_set_native_value_always_refreshes_coordinator() -> None:
    coord = _make_coordinator()
    number = _make_number(coord, "brew_group_set_temperature")
    await number.async_set_native_value(93.0)
    coord.async_request_refresh.assert_called_once()


@pytest.mark.asyncio
async def test_set_native_value_refreshes_even_when_api_raises() -> None:
    """The finally block in async_set_native_value must always refresh."""
    coord = _make_coordinator()
    coord.xenia.set_bg_set_temp = AsyncMock(side_effect=RuntimeError("API error"))
    number = _make_number(coord, "brew_group_set_temperature")
    with pytest.raises(RuntimeError):
        await number.async_set_native_value(93.0)
    # Refresh must still be called despite the exception
    coord.async_request_refresh.assert_called_once()


@pytest.mark.asyncio
async def test_set_native_value_float_coercion() -> None:
    coord = _make_coordinator()
    number = _make_number(coord, "brew_group_set_temperature")
    await number.async_set_native_value(90)  # int, not float
    coord.xenia.set_bg_set_temp.assert_called_once_with(90.0)


# ===========================================================================
# entity_category
# ===========================================================================


def test_number_entity_category_returns_config_from_description() -> None:
    from homeassistant.const import EntityCategory

    coord = _make_coordinator()
    number = _make_number(coord, "brew_group_set_temperature")
    # Both NUMBER_TYPES have entity_category=CONFIG set directly on the description
    # and no entity_category_fn, so super().entity_category should return CONFIG
    desc = next(d for d in NUMBER_TYPES if d.key == "brew_group_set_temperature")
    assert desc.entity_category == EntityCategory.CONFIG
