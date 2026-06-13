from __future__ import annotations

import shlex

from ros2unbag.cli.repl_config import FLAG_OPTIONS


def split_repl_line(line: str) -> list[str]:
    """Split REPL input while preserving common Windows path syntax.

    ``posix=False`` keeps backslashes intact, which matters for paths such as
    ``.\\bag\\demo`` in PowerShell sessions.
    """
    try:
        tokens = shlex.split(line, posix=False)
    except ValueError as exc:
        raise ValueError(f"Could not parse input: {exc}") from exc
    return [_strip_quotes(token) for token in tokens]


def parse_args(args: list[str]) -> tuple[list[str], dict[str, str]]:
    positionals: list[str] = []
    options: dict[str, str] = {}
    index = 0
    while index < len(args):
        token = args[index]
        if token.startswith("--") and "=" in token:
            key, value = token.split("=", 1)
            options[key] = value
            index += 1
            continue
        if token in FLAG_OPTIONS:
            options[token] = "true"
            index += 1
            continue
        if token.startswith("-"):
            if index + 1 >= len(args):
                raise ValueError(f"Missing value for {token}")
            options[token] = args[index + 1]
            index += 2
            continue
        positionals.append(token)
        index += 1
    return positionals, options


def option(options: dict[str, str], *names: str) -> str | None:
    for name in names:
        if name in options:
            return options[name]
    return None


def flag(options: dict[str, str], *names: str) -> bool:
    return any(name in options for name in names)


def _strip_quotes(token: str) -> str:
    if len(token) >= 2 and token[0] == token[-1] and token[0] in {"'", '"'}:
        return token[1:-1]
    return token
