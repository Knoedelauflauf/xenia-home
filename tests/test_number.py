"""Tests for number.py — XeniaNumber, XeniaWeightNumber, and NUMBER_TYPES."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.xenia_home.coordinator import (
    XeniaConfigData,
    XeniaCoordinatorData,
)
from custom_components.xenia_home.number import (
    NUMBER_TYPES,
    XeniaNumber,
    XeniaWeightNumber,
)
from custom_components.xenia_home.xenia import (
    XeniaMachineData,
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
    coord.data = XeniaCoordinatorData(
        overview=overview, overview_single=overview_single
    )
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
    assert number.entity_description.entity_category == EntityCategory.CONFIG


# ===========================================================================
# XeniaWeightNumber — helpers
# ===========================================================================


def _make_config_coordinator(
    instruction: str | None = "1;13;27 45;7;",
    managed_name: str | None = "Test Shot",
    options: dict | None = None,
) -> MagicMock:
    """Build a mock XeniaConfigCoordinator for weight number tests."""
    coord = MagicMock()
    coord.config_entry = MagicMock()
    coord.config_entry.data = {"host": "xenia.local"}
    coord.config_entry.options = options or {
        "weight_management_enabled": True,
        "managed_script_id": 17,
    }
    coord.xenia = MagicMock()
    coord.xenia.read_script = AsyncMock(
        return_value={"Content": instruction or "", "Title": managed_name or ""}
    )
    coord.xenia.update_script = AsyncMock()
    coord.async_request_refresh = AsyncMock()

    machine = XeniaMachineData.from_dict(
        {"MA_TYPE": 1, "FW_VERSION_MAJOR": 2, "FW_VERSION_MINOR": 3}
    )
    coord.data = XeniaConfigData(
        machine=machine,
        managed_script_instruction=instruction,
        managed_script_name=managed_name,
    )
    return coord


def _make_weight_number(coordinator: MagicMock) -> XeniaWeightNumber:
    """Build a XeniaWeightNumber with a mocked coordinator."""
    with patch(
        "homeassistant.helpers.update_coordinator.CoordinatorEntity.__init__",
        return_value=None,
    ):
        number = XeniaWeightNumber.__new__(XeniaWeightNumber)
        number.coordinator = coordinator
        number.hass = MagicMock()
        XeniaWeightNumber.__init__(number, coordinator)
    return number


# ===========================================================================
# XeniaWeightNumber — native_value
# ===========================================================================


def test_weight_number_returns_weight_from_instruction() -> None:
    coord = _make_config_coordinator(instruction="1;13;27 45;7;")
    number = _make_weight_number(coord)
    assert number.native_value == pytest.approx(45.0)


def test_weight_number_returns_last_weight_from_multiple_commands() -> None:
    coord = _make_config_coordinator(instruction="1;13;27 2;3 70 5000;27 45;17;7;")
    number = _make_weight_number(coord)
    assert number.native_value == pytest.approx(45.0)


def test_weight_number_returns_none_when_no_instruction() -> None:
    coord = _make_config_coordinator(instruction=None)
    number = _make_weight_number(coord)
    assert number.native_value is None


def test_weight_number_returns_none_when_no_weight_command() -> None:
    coord = _make_config_coordinator(instruction="1;13;7;")
    number = _make_weight_number(coord)
    assert number.native_value is None


# ===========================================================================
# XeniaWeightNumber — available
# ===========================================================================


def test_weight_number_available_when_enabled_and_instruction_present() -> None:
    coord = _make_config_coordinator()
    number = _make_weight_number(coord)
    assert number.available is True


def test_weight_number_unavailable_when_disabled() -> None:
    coord = _make_config_coordinator(
        options={"weight_management_enabled": False, "managed_script_id": 17}
    )
    number = _make_weight_number(coord)
    assert number.available is False


def test_weight_number_unavailable_when_instruction_is_none() -> None:
    coord = _make_config_coordinator(
        instruction=None,
        options={"weight_management_enabled": True, "managed_script_id": 17},
    )
    number = _make_weight_number(coord)
    assert number.available is False


# ===========================================================================
# XeniaWeightNumber — async_set_native_value
# ===========================================================================


@pytest.mark.asyncio
async def test_weight_number_set_reads_fresh_then_writes_back() -> None:
    """Setting weight should read current script, modify it, and write back."""
    coord = _make_config_coordinator(instruction="1;13;27 45;7;")
    coord.xenia.read_script = AsyncMock(
        return_value={"Content": "1;13;27 45;7;", "Title": "Test Shot"}
    )
    number = _make_weight_number(coord)
    await number.async_set_native_value(50.0)

    # Should have read the script fresh first
    coord.xenia.read_script.assert_called_once_with(17)
    # Should have written the updated instruction
    coord.xenia.update_script.assert_called_once()
    call_args = coord.xenia.update_script.call_args
    written_instruction = call_args[0][2]
    assert "27 50" in written_instruction
    # Should refresh the coordinator
    coord.async_request_refresh.assert_called_once()


@pytest.mark.asyncio
async def test_weight_number_set_does_nothing_when_no_script_id() -> None:
    coord = _make_config_coordinator(options={"weight_management_enabled": True})
    number = _make_weight_number(coord)
    await number.async_set_native_value(50.0)
    coord.xenia.read_script.assert_not_called()
    coord.xenia.update_script.assert_not_called()


@pytest.mark.asyncio
async def test_weight_number_set_does_nothing_when_read_returns_no_content() -> None:
    coord = _make_config_coordinator()
    coord.xenia.read_script = AsyncMock(return_value={})
    number = _make_weight_number(coord)
    await number.async_set_native_value(50.0)
    coord.xenia.update_script.assert_not_called()


@pytest.mark.asyncio
async def test_weight_number_set_preserves_other_commands() -> None:
    """Setting weight should only modify the weight command, not other parts."""
    coord = _make_config_coordinator(instruction="1;13;3 70 5000;27 40;17;7;")
    coord.xenia.read_script = AsyncMock(
        return_value={"Content": "1;13;3 70 5000;27 40;17;7;", "Title": "Test"}
    )
    number = _make_weight_number(coord)
    await number.async_set_native_value(42.0)

    written_instruction = coord.xenia.update_script.call_args[0][2]
    # Other commands should still be there
    assert "3 70 5000" in written_instruction
    assert "27 42" in written_instruction


# ===========================================================================
# XeniaWeightNumber — min/max/step from options
# ===========================================================================


def test_weight_number_uses_defaults_when_no_options_set() -> None:
    coord = _make_config_coordinator(
        options={"weight_management_enabled": True, "managed_script_id": 17}
    )
    number = _make_weight_number(coord)
    assert number._attr_native_min_value == 25.0
    assert number._attr_native_max_value == 50.0
    assert number._attr_native_step == 0.5


def test_weight_number_reads_min_max_step_from_options() -> None:
    coord = _make_config_coordinator(
        options={
            "weight_management_enabled": True,
            "managed_script_id": 17,
            "weight_min": 10.0,
            "weight_max": 60.0,
            "weight_step": 0.1,
        }
    )
    number = _make_weight_number(coord)
    assert number._attr_native_min_value == 10.0
    assert number._attr_native_max_value == 60.0
    assert number._attr_native_step == 0.1


def test_weight_number_partial_options_uses_defaults_for_missing() -> None:
    coord = _make_config_coordinator(
        options={
            "weight_management_enabled": True,
            "managed_script_id": 17,
            "weight_min": 15.0,
        }
    )
    number = _make_weight_number(coord)
    assert number._attr_native_min_value == 15.0
    assert number._attr_native_max_value == 50.0  # default
    assert number._attr_native_step == 0.5  # default
