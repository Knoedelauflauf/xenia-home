"""Tests for the script instruction parser."""

import pytest

from custom_components.xenia_home.script_parser import (
    COMMAND_WEIGHT_TARGET,
    get_weight_target,
    parse_instruction,
    set_weight_target,
)


@pytest.mark.parametrize(
    ("instruction", "expected"),
    [
        ("1;13;3 70 5000;27 45;17;7;", "1;13;3 70 5000;27 45;17;7;"),
        ("1;13;7", "1;13;7;"),
        (" 1 ; 13;;7; ", "1;13;7;"),
        ("", ""),
    ],
)
def test_round_trip(instruction: str, expected: str) -> None:
    """Parsing and serializing keeps every command and normalizes the format."""
    assert parse_instruction(instruction).to_instruction() == expected


def test_has_command() -> None:
    """has_command tells whether a command id occurs."""
    parsed = parse_instruction("1;27 40;7;")
    assert parsed.has_command(COMMAND_WEIGHT_TARGET)
    assert not parsed.has_command(99)


@pytest.mark.parametrize(
    ("instruction", "expected"),
    [
        ("1;13;3 70 5000;27 45;17;7;", 45.0),
        ("1;27 36.5;7;", 36.5),
        ("1;27 0;7;", 0.0),
        ("1;27 2;3 70 5000;27 45;17;7;", 45.0),
        ("1;27 45;27;7;", 45.0),
        ("1;13;7;", None),
    ],
)
def test_get_weight_target(instruction: str, expected: float | None) -> None:
    """The weight target is the last weight command with a value."""
    assert get_weight_target(instruction) == expected


@pytest.mark.parametrize(
    ("instruction", "weight", "expected"),
    [
        ("1;13;3 70 5000;27 45;17;7;", 38.0, "1;13;3 70 5000;27 38;17;7;"),
        ("1;27 45;7;", 36.5, "1;27 36.5;7;"),
        ("1;27 2;3 70 5000;27 45;17;7;", 38.0, "1;27 2;3 70 5000;27 38;17;7;"),
        ("1;27;7;", 40.0, "1;27 40;7;"),
        ("1;13;7;", 42.0, "1;13;27 42;7;"),
        ("", 42.0, "27 42;"),
    ],
)
def test_set_weight_target(instruction: str, weight: float, expected: str) -> None:
    """Only the last weight command changes; without one it is added before the end."""
    assert set_weight_target(instruction, weight) == expected
