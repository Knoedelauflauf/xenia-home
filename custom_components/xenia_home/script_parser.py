"""Read and change the weight target of Xenia script instructions.

An instruction is a list of semicolon separated commands, each an integer
command id followed by space separated arguments, for example
``1;13;3 70 5000;27 45;17;7;``. Commands are kept as they are, so an
instruction survives a round trip unchanged.
"""

from dataclasses import dataclass

COMMAND_WEIGHT_TARGET = 27


@dataclass
class ScriptCommand:
    """One command of an instruction."""

    command_id: int
    args: list[str]


@dataclass
class ParsedScript:
    """The commands of an instruction, in order."""

    commands: list[ScriptCommand]

    def to_instruction(self) -> str:
        """Return the instruction, ending with a semicolon."""
        return "".join(
            f"{' '.join([str(c.command_id), *c.args])};" for c in self.commands
        )

    def has_command(self, command_id: int) -> bool:
        """Return whether the instruction contains `command_id`."""
        return any(c.command_id == command_id for c in self.commands)


def parse_instruction(instruction: str) -> ParsedScript:
    """Parse an instruction."""
    return ParsedScript(
        [
            ScriptCommand(int(parts[0]), parts[1:])
            for segment in instruction.split(";")
            if (parts := segment.split())
        ]
    )


def get_weight_target(instruction: str) -> float | None:
    """Return the weight target of an instruction.

    A script can have several weight commands, for example one that ends the
    preinfusion; the last one is the target of the shot.
    """
    command = next(
        (
            c
            for c in reversed(parse_instruction(instruction).commands)
            if c.command_id == COMMAND_WEIGHT_TARGET and c.args
        ),
        None,
    )
    return None if command is None else float(command.args[0])


def set_weight_target(instruction: str, weight: float) -> str:
    """Return the instruction with the weight target set to `weight`.

    Without a weight command, one is added before the last command, which
    ends the script.
    """
    parsed = parse_instruction(instruction)
    value = f"{weight:g}"
    command = next(
        (c for c in reversed(parsed.commands) if c.command_id == COMMAND_WEIGHT_TARGET),
        None,
    )
    if command is None:
        parsed.commands.insert(
            max(len(parsed.commands) - 1, 0),
            ScriptCommand(COMMAND_WEIGHT_TARGET, [value]),
        )
    elif command.args:
        command.args[0] = value
    else:
        command.args.append(value)
    return parsed.to_instruction()
