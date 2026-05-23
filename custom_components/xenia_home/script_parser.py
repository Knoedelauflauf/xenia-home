"""Parse and modify Xenia espresso machine script instructions.

Script instructions use a semicolon-separated format where each segment is a
command.  A command consists of an integer command ID optionally followed by
space-separated arguments.  Example::

    1;13;3 70 5000;27 45;17;7;

This module provides helpers to read and modify individual command values while
preserving unknown commands (round-trip safe).
"""

from dataclasses import dataclass, field

# Well-known command IDs
COMMAND_WEIGHT_TARGET = 27


@dataclass
class ScriptCommand:
    """A single command inside a script instruction."""

    command_id: int
    args: list[str] = field(default_factory=list)

    def to_segment(self) -> str:
        """Serialize back to the semicolon-separated segment string."""
        parts = [str(self.command_id), *self.args]
        return " ".join(parts)


@dataclass
class ParsedScript:
    """A parsed script instruction consisting of ordered commands."""

    commands: list[ScriptCommand] = field(default_factory=list)

    def to_instruction(self) -> str:
        """Serialize the full instruction string (trailing semicolon)."""
        return ";".join(cmd.to_segment() for cmd in self.commands) + ";"

    def has_command(self, command_id: int) -> bool:
        """Return True if *command_id* is present."""
        return any(c.command_id == command_id for c in self.commands)

    def get_command_value(self, command_id: int) -> str | None:
        """Return the first argument of *command_id*, or None."""
        for cmd in self.commands:
            if cmd.command_id == command_id and cmd.args:
                return cmd.args[0]
        return None

    def get_last_command_value(self, command_id: int) -> str | None:
        """Return the first argument of the *last* occurrence of *command_id*."""
        for cmd in reversed(self.commands):
            if cmd.command_id == command_id and cmd.args:
                return cmd.args[0]
        return None

    def set_last_command_value(self, command_id: int, value: str) -> None:
        """Set the first argument of the *last* occurrence of *command_id*.

        If no occurrence exists, falls back to ``set_command_value`` (insert).
        """
        for cmd in reversed(self.commands):
            if cmd.command_id == command_id:
                if cmd.args:
                    cmd.args[0] = value
                else:
                    cmd.args.append(value)
                return
        # Not found — insert a new command
        self.set_command_value(command_id, value)

    def set_command_value(self, command_id: int, value: str) -> None:
        """Set the first argument of *command_id*.

        If the command exists, its first argument is replaced (or appended).
        If it does not exist, the command is inserted before the last command
        (which is typically the terminating ``7``).
        """
        for cmd in self.commands:
            if cmd.command_id == command_id:
                if cmd.args:
                    cmd.args[0] = value
                else:
                    cmd.args.append(value)
                return
        new_cmd = ScriptCommand(command_id=command_id, args=[value])
        # Insert before the last command if possible (usually the stop cmd)
        if self.commands:
            self.commands.insert(len(self.commands) - 1, new_cmd)
        else:
            self.commands.append(new_cmd)


def parse_instruction(instruction: str) -> ParsedScript:
    """Parse a semicolon-separated instruction string into a ParsedScript."""
    commands: list[ScriptCommand] = []
    for segment in instruction.split(";"):
        segment = segment.strip()
        if not segment:
            continue
        parts = segment.split()
        command_id = int(parts[0])
        args = parts[1:]
        commands.append(ScriptCommand(command_id=command_id, args=args))
    return ParsedScript(commands=commands)


def get_weight_target(instruction: str) -> float | None:
    """Extract the final weight target (last command 27) from an instruction.

    Scripts may contain multiple weight commands (e.g. preinfusion weight
    followed by the final target weight).  The last one is the brew target.
    """
    parsed = parse_instruction(instruction)
    value = parsed.get_last_command_value(COMMAND_WEIGHT_TARGET)
    if value is None:
        return None
    return float(value)


def set_weight_target(instruction: str, weight: float) -> str:
    """Return a new instruction with the final weight target set to *weight*.

    Only the last command 27 is modified; earlier weight commands (e.g.
    preinfusion thresholds) are preserved.
    """
    parsed = parse_instruction(instruction)
    if weight == int(weight):
        value_str = str(int(weight))
    else:
        value_str = f"{weight:g}"
    parsed.set_last_command_value(COMMAND_WEIGHT_TARGET, value_str)
    return parsed.to_instruction()
