"""Tests for the script instruction parser."""

import pytest

from custom_components.xenia_home.script_parser import (
    COMMAND_WEIGHT_TARGET,
    ScriptCommand,
    get_weight_target,
    parse_instruction,
    set_weight_target,
)

# ---------------------------------------------------------------------------
# parse_instruction
# ---------------------------------------------------------------------------


def test_parse_typical_instruction():
    parsed = parse_instruction("1;13;3 70 5000;27 45;17;7;")
    assert len(parsed.commands) == 6
    assert parsed.commands[0] == ScriptCommand(1, [])
    assert parsed.commands[2] == ScriptCommand(3, ["70", "5000"])
    assert parsed.commands[3] == ScriptCommand(27, ["45"])


def test_parse_empty_string():
    parsed = parse_instruction("")
    assert parsed.commands == []


def test_parse_single_command():
    parsed = parse_instruction("7;")
    assert len(parsed.commands) == 1
    assert parsed.commands[0] == ScriptCommand(7, [])


# ---------------------------------------------------------------------------
# Round-trip safety
# ---------------------------------------------------------------------------


def test_roundtrip_preserves_instruction():
    original = "1;13;3 70 5000;27 45;17;7;"
    result = parse_instruction(original).to_instruction()
    assert result == original


def test_roundtrip_no_trailing_semicolon_input():
    """Input without trailing semicolon still produces canonical output."""
    result = parse_instruction("1;13;7").to_instruction()
    assert result == "1;13;7;"


# ---------------------------------------------------------------------------
# has_command / get_command_value / set_command_value
# ---------------------------------------------------------------------------


def test_has_command():
    parsed = parse_instruction("1;27 40;7;")
    assert parsed.has_command(27) is True
    assert parsed.has_command(99) is False


def test_get_command_value():
    parsed = parse_instruction("1;27 42;7;")
    assert parsed.get_command_value(27) == "42"


def test_get_command_value_missing():
    parsed = parse_instruction("1;7;")
    assert parsed.get_command_value(27) is None


def test_get_command_value_no_args():
    parsed = parse_instruction("1;13;7;")
    assert parsed.get_command_value(13) is None


def test_set_command_value_existing():
    parsed = parse_instruction("1;27 40;7;")
    parsed.set_command_value(27, "50")
    assert parsed.get_command_value(27) == "50"
    assert parsed.to_instruction() == "1;27 50;7;"


def test_set_command_value_insert_new():
    parsed = parse_instruction("1;13;7;")
    parsed.set_command_value(27, "35")
    assert parsed.has_command(27)
    # Should be inserted before the last command (7)
    assert parsed.to_instruction() == "1;13;27 35;7;"


# ---------------------------------------------------------------------------
# get_weight_target / set_weight_target
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("instruction", "expected"),
    [
        ("1;13;3 70 5000;27 45;17;7;", 45.0),
        ("1;27 36.5;7;", 36.5),
        ("1;27 0;7;", 0.0),
    ],
)
def test_get_weight_target_reads_command_27(instruction, expected):
    assert get_weight_target(instruction) == expected


def test_get_weight_target_missing():
    assert get_weight_target("1;13;7;") is None


def test_set_weight_target_existing():
    result = set_weight_target("1;13;3 70 5000;27 45;17;7;", 38.0)
    assert get_weight_target(result) == 38.0
    # Other commands preserved
    parsed = parse_instruction(result)
    assert len(parsed.commands) == 6


def test_set_weight_target_integer():
    result = set_weight_target("1;27 45;7;", 40.0)
    assert "27 40;" in result


def test_set_weight_target_decimal():
    result = set_weight_target("1;27 45;7;", 36.5)
    assert "27 36.5;" in result


def test_get_weight_target_multiple_returns_last():
    """With two weight commands, get_weight_target returns the last (brew target)."""
    assert get_weight_target("1;27 2;3 70 5000;27 45;17;7;") == 45.0


def test_set_weight_target_multiple_changes_only_last():
    """With two weight commands, only the last one (brew target) is modified."""
    result = set_weight_target("1;27 2;3 70 5000;27 45;17;7;", 38.0)
    assert get_weight_target(result) == 38.0
    # The first weight command (preinfusion) is preserved
    parsed = parse_instruction(result)
    weight_cmds = [c for c in parsed.commands if c.command_id == 27]
    assert len(weight_cmds) == 2
    assert weight_cmds[0].args[0] == "2"
    assert weight_cmds[1].args[0] == "38"


def test_set_weight_target_insert_when_missing():
    result = set_weight_target("1;13;7;", 42.0)
    assert get_weight_target(result) == 42.0
    # The new command should be before the terminal 7
    parsed = parse_instruction(result)
    assert parsed.commands[-1].command_id == 7
    assert parsed.commands[-2].command_id == COMMAND_WEIGHT_TARGET
