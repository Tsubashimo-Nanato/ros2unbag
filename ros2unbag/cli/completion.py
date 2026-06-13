from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

from ros2unbag.cli.parsing import split_repl_line
from ros2unbag.cli.repl_config import (
    BACKEND_CHOICES,
    COMMANDS,
    FLAG_OPTIONS,
    OPTIONS_BY_COMMAND,
    SOURCE_CHOICES,
    VALUE_OPTIONS,
    VIEW_CHOICES,
)
from ros2unbag.core.session import ALL_EXPORTS, Session, compatible_export_formats


class Ros2UnbagCompleter(Completer):
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_completions(self, document: Document, complete_event: object) -> Iterable[Completion]:
        text = document.text_before_cursor
        current = _current_word(text)
        tokens = _completion_tokens(text)
        if not tokens:
            yield from _complete_values(COMMANDS, current)
            return

        command = tokens[0].lower()
        if len(tokens) == 1 and not text.endswith((" ", "\t")):
            yield from _complete_values(COMMANDS, current)
            return

        previous = tokens[-2] if len(tokens) >= 2 else ""
        if previous in {"--format", "-f"}:
            yield from _complete_values(self._export_format_values(command, tokens, current), current)
            return
        if previous in {"--topic", "-t"}:
            yield from _complete_values(self._topic_names(), current)
            return
        if previous == "--dur":
            yield from _complete_values(self._topic_names(), current)
            return
        if previous in {"--view", "-v"}:
            yield from _complete_values(VIEW_CHOICES, current)
            return
        if previous == "--fps":
            return
        if previous == "--source":
            yield from _complete_values(SOURCE_CHOICES, current)
            return
        if previous in {"--out", "-o", "--backend"}:
            if previous == "--backend":
                yield from _complete_values(BACKEND_CHOICES, current)
            else:
                yield from _complete_paths(current)
            return
        if current.startswith("-"):
            yield from _complete_option_values(
                _available_options(command, _completed_args(tokens[1:], current)),
                current,
            )
            return

        yield from self._complete_next_argument(command, tokens, current)

    def _topic_names(self) -> list[str]:
        return sorted(topic.name for topic in self.session.topics)

    def _export_format_values(self, command: str, tokens: list[str], current: str) -> list[str]:
        if command not in {"export", "export-select"}:
            return sorted(ALL_EXPORTS)

        args = _completed_args(tokens[1:], current)
        positionals, options, _expecting_value = _completion_state(args)
        selected_topic = options.get("--topic") or options.get("-t")
        if selected_topic is None and positionals:
            selected_topic = positionals[0]
        topic_info = next(
            (topic for topic in self.session.topics if topic.name == selected_topic),
            None,
        )
        if topic_info is None:
            return sorted(ALL_EXPORTS)
        return compatible_export_formats(topic_info)

    def _complete_next_argument(
        self,
        command: str,
        tokens: list[str],
        current: str,
    ) -> Iterable[Completion]:
        args = _completed_args(tokens[1:], current)
        positionals, options, expecting_value = _completion_state(args)
        if expecting_value is not None:
            return

        if command == "open":
            if not positionals:
                yield from _complete_paths(current)
            else:
                yield from _complete_option_values(_available_options(command, args), current)
            return
        if command == "scan":
            if not positionals and (self.session.reader is None or current):
                yield from _complete_paths(current)
            elif not positionals and not options and not current:
                yield from _complete_option_values(["--all"], current)
            else:
                yield from _complete_option_values(_available_options(command, args), current)
            return
        if command == "topics":
            if not positionals and not options and not current:
                yield from _complete_option_values(["-all", "-s"], current)
            else:
                yield from _complete_option_values(_available_options(command, args), current)
            return
        if command in {"export", "export-select"}:
            if "--topic" in options or "-t" in options:
                if "--format" not in options and "-f" not in options:
                    yield from _complete_option_values(["--format"], current)
                    return
            elif not positionals:
                yield from _complete_values(self._topic_names(), current)
                return
            elif "--format" not in options and "-f" not in options:
                yield from _complete_option_values(["--format"], current)
                return

            if "--out" not in options and "-o" not in options:
                yield from _complete_option_values(["--out"], current)
                return
            if _selected_format(options) == "mp4" and "--fps" not in options:
                yield from _complete_option_values(["--fps"], current)
            return
        if command == "export-all":
            if "--out" not in options and "-o" not in options:
                yield from _complete_option_values(["--out"], current)
            return
        if command == "inspect":
            remaining = _available_options(command, args)
            if remaining:
                yield from _complete_option_values(remaining, current)
            return
        if command == "dur":
            if not positionals:
                yield from _complete_values(self._topic_names(), current)
            return
        if command == "gui":
            if not positionals:
                yield from _complete_paths(current)
            return
        if command == "upgrade":
            yield from _complete_option_values(_available_options(command, args), current)
            return


class ExportSelectCompleter(Completer):
    def __init__(self, session: Session) -> None:
        self.base = Ros2UnbagCompleter(session)

    def get_completions(self, document: Document, complete_event: object) -> Iterable[Completion]:
        current = _current_word(document.text_before_cursor)
        text = document.text_before_cursor
        if not text.strip() or (" " not in text.strip() and not text.endswith((" ", "\t"))):
            yield from _complete_values(["export-all", "cancel"], current)
        wrapped = Document("export " + document.text_before_cursor)
        yield from self.base.get_completions(wrapped, complete_event)


def _current_word(text: str) -> str:
    if not text or text[-1].isspace():
        return ""
    return text.split()[-1]


def _completion_tokens(text: str) -> list[str]:
    if not text.strip():
        return []
    try:
        tokens = split_repl_line(text)
    except ValueError:
        return text.split()
    if text.endswith((" ", "\t")):
        tokens.append("")
    return tokens


def _completion_state(args: list[str]) -> tuple[list[str], dict[str, str | None], str | None]:
    positionals: list[str] = []
    options: dict[str, str | None] = {}
    expecting_value: str | None = None
    index = 0
    while index < len(args):
        token = args[index]
        if token in VALUE_OPTIONS:
            if index == len(args) - 1:
                expecting_value = token
                options[token] = None
                break
            options[token] = args[index + 1]
            index += 2
            continue
        if token.startswith("--") and "=" in token:
            key, value = token.split("=", 1)
            options[key] = value
            index += 1
            continue
        if token in FLAG_OPTIONS:
            options[token] = None
            index += 1
            continue
        if token.startswith("-"):
            options[token] = None
            index += 1
            continue
        positionals.append(token)
        index += 1
    return positionals, options, expecting_value


def _completed_args(args: list[str], current: str) -> list[str]:
    if current:
        return args[:-1]
    if args and args[-1] == "":
        return args[:-1]
    return args


def _available_options(command: str, args: list[str]) -> list[str]:
    _positionals, used_options, _expecting_value = _completion_state(args)
    options = OPTIONS_BY_COMMAND.get(command, [])
    return [
        option
        for option in options
        if option not in used_options and _paired_option(option) not in used_options
    ]


def _paired_option(option: str) -> str:
    pairs = {
        "--format": "-f",
        "-f": "--format",
        "--out": "-o",
        "-o": "--out",
        "--view": "-v",
        "-v": "--view",
        "--topic": "-t",
        "-t": "--topic",
        "--all": "-all",
        "-all": "--all",
        "--select": "-s",
        "-s": "--select",
    }
    return pairs.get(option, "")


def _selected_format(options: dict[str, str | None]) -> str | None:
    value = options.get("--format") or options.get("-f")
    return value.lower() if value else None


def _complete_values(values: Iterable[str], current: str) -> Iterable[Completion]:
    for value in values:
        if value.startswith(current):
            yield Completion(value, start_position=-len(current))


def _complete_option_values(values: Iterable[str], current: str) -> Iterable[Completion]:
    for value in values:
        if value.startswith(current):
            yield Completion(f"{value} ", start_position=-len(current))


def _complete_paths(current: str) -> Iterable[Completion]:
    path_text = current or "."
    expanded = Path(path_text).expanduser()
    if path_text.endswith(("/", "\\")):
        directory = expanded
        prefix = ""
    else:
        directory = expanded.parent if expanded.parent != Path("") else Path(".")
        prefix = expanded.name
    if not directory.exists() or not directory.is_dir():
        return
    for child in sorted(directory.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
        if not child.name.startswith(prefix):
            continue
        replacement = child.name + ("\\" if child.is_dir() else "")
        if directory != Path("."):
            replacement = str(directory / replacement)
        yield Completion(replacement, start_position=-len(current))
