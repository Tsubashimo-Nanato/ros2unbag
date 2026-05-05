from __future__ import annotations

import os
from pathlib import Path
import shlex
import sys
from typing import Iterable

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.history import FileHistory

from ros2_unbag.cli.render import (
    console,
    render_export_result,
    render_export_results,
    render_inspect_results,
    render_scan_view,
    render_topic_duration,
    render_warnings,
)
from ros2_unbag.core.manifest import write_manifest, write_topics_csv
from ros2_unbag.core.session import ALL_EXPORTS, Session

COMMANDS = [
    "open",
    "close",
    "scan",
    "topics",
    "export",
    "export-all",
    "inspect",
    "dur",
    "help",
    "clear",
    "exit",
    "quit",
]

OPTIONS_BY_COMMAND = {
    "open": ["--backend"],
    "scan": ["--out", "-o", "--view", "-v", "--backend"],
    "topics": ["--view", "-v"],
    "export": ["--topic", "-t", "--format", "-f", "--out", "-o", "--fps"],
    "export-all": ["--out", "-o"],
    "inspect": ["--time"],
    "dur": [],
}

VIEW_CHOICES = ["table", "tree", "nav"]


def run_repl() -> None:
    session = Session()
    try:
        prompt = PromptSession(
            history=FileHistory(".ros2unbag_history"),
            completer=Ros2UnbagCompleter(session),
            complete_while_typing=False,
        )
    except Exception:
        if sys.stdin.isatty():
            raise
        _run_plain_repl(session)
        return
    console.print("ros2unbag interactive shell. Type [bold]help[/bold] for commands.")
    try:
        while True:
            try:
                line = prompt.prompt("ros2unbag> ")
            except KeyboardInterrupt:
                continue
            except EOFError:
                break
            should_exit = dispatch_repl_line(session, line)
            if should_exit:
                break
    finally:
        session.close()


def _run_plain_repl(session: Session) -> None:
    console.print("ros2unbag interactive shell. Type [bold]help[/bold] for commands.")
    try:
        for line in sys.stdin:
            console.print("ros2unbag> " + line.rstrip(), soft_wrap=False)
            should_exit = dispatch_repl_line(session, line)
            if should_exit:
                break
    finally:
        session.close()


def dispatch_repl_line(session: Session, line: str) -> bool:
    tokens = split_repl_line(line)
    if not tokens:
        return False

    command = tokens[0].lower()
    args = tokens[1:]
    try:
        if command in {"exit", "quit"}:
            return True
        if command == "help":
            render_repl_help()
            return False
        if command == "clear":
            os.system("cls" if os.name == "nt" else "clear")
            return False
        if command == "open":
            _handle_open(session, args)
            return False
        if command == "close":
            session.close()
            console.print("Closed current bag.")
            return False
        if command == "scan":
            _handle_scan(session, args)
            return False
        if command == "topics":
            _handle_topics(session, args)
            return False
        if command == "export":
            _handle_export(session, args)
            return False
        if command == "export-all":
            _handle_export_all(session, args)
            return False
        if command == "inspect":
            _handle_inspect(session, args)
            return False
        if command == "dur":
            _handle_duration(session, args)
            return False
        console.print(f"[red]Unknown command:[/red] {command}")
        console.print("Type [bold]help[/bold] for available commands.")
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
    return False


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


def _strip_quotes(token: str) -> str:
    if len(token) >= 2 and token[0] == token[-1] and token[0] in {"'", '"'}:
        return token[1:-1]
    return token


def _parse_args(args: list[str]) -> tuple[list[str], dict[str, str]]:
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
        if token.startswith("-"):
            if index + 1 >= len(args):
                raise ValueError(f"Missing value for {token}")
            options[token] = args[index + 1]
            index += 2
            continue
        positionals.append(token)
        index += 1
    return positionals, options


def _option(options: dict[str, str], *names: str) -> str | None:
    for name in names:
        if name in options:
            return options[name]
    return None


def _handle_open(session: Session, args: list[str]) -> None:
    positionals, options = _parse_args(args)
    if not positionals:
        raise ValueError("Usage: open BAG_PATH")
    backend = _option(options, "--backend") or session.backend
    topics = session.open_bag(positionals[0], backend=backend)
    console.print(f"Opened [bold]{session.bag_path}[/bold] ({len(topics)} topics).")
    render_warnings(list(getattr(session.reader, "warnings", [])) if session.reader else [])


def _handle_scan(session: Session, args: list[str]) -> None:
    positionals, options = _parse_args(args)
    if positionals:
        backend = _option(options, "--backend") or session.backend
        session.open_bag(positionals[0], backend=backend)
    manifest = session.scan()
    render_scan_view(manifest.topics, view=_option(options, "--view", "-v") or "table")
    render_warnings(manifest.warnings)
    out = _option(options, "--out", "-o")
    if out:
        out_path = Path(out)
        out_path.mkdir(parents=True, exist_ok=True)
        manifest_path = write_manifest(manifest, out_path / "manifest.json")
        topics_path = write_topics_csv(manifest.topics, out_path / "topics.csv")
        console.print(f"Wrote [bold]{manifest_path}[/bold]")
        console.print(f"Wrote [bold]{topics_path}[/bold]")


def _handle_topics(session: Session, args: list[str]) -> None:
    _positionals, options = _parse_args(args)
    render_scan_view(session.list_topics(), view=_option(options, "--view", "-v") or "table")


def _handle_export(session: Session, args: list[str]) -> None:
    positionals, options = _parse_args(args)
    topic = _option(options, "--topic", "-t") or (positionals[0] if positionals else None)
    fmt = _option(options, "--format", "-f")
    out = _option(options, "--out", "-o")
    fps = float(_option(options, "--fps") or 30.0)
    if topic is None or fmt is None or out is None:
        raise ValueError("Usage: export TOPIC --format FORMAT --out OUT_DIR [--fps FPS]")
    result = session.export_topic(topic, fmt, out, fps=fps)
    render_export_result(result)


def _handle_export_all(session: Session, args: list[str]) -> None:
    _positionals, options = _parse_args(args)
    out = _option(options, "--out", "-o")
    if out is None:
        raise ValueError("Usage: export-all --out OUT_DIR")
    manifest, results = session.export_all(out)
    render_export_results(results)
    render_warnings(manifest.warnings)
    console.print(f"Wrote [bold]{Path(out) / 'manifest.json'}[/bold]")


def _handle_inspect(session: Session, args: list[str]) -> None:
    _positionals, options = _parse_args(args)
    raw_time = _option(options, "--time")
    if raw_time is None:
        raise ValueError("Usage: inspect --time SECONDS")
    target_ns, results, warnings = session.inspect_time(float(raw_time))
    render_inspect_results(target_ns, results, warnings)


def _handle_duration(session: Session, args: list[str]) -> None:
    positionals, _options = _parse_args(args)
    if not positionals:
        raise ValueError("Usage: dur TOPIC")
    render_topic_duration(session.topic_duration(positionals[0]))


def render_repl_help() -> None:
    console.print("Commands:")
    console.print("  open BAG_PATH [--backend auto|rosbags|sqlite]")
    console.print("  scan [BAG_PATH] [--view table|tree|nav] [--out OUT_DIR]")
    console.print("  topics [--view table|tree|nav]")
    console.print("  dur TOPIC")
    console.print("  inspect --time SECONDS")
    console.print("  export TOPIC --format csv|parquet|sqlite|png|jpg|mp4|jsonl|raw --out OUT_DIR [--fps FPS]")
    console.print("  export-all --out OUT_DIR")
    console.print("  close")
    console.print("  clear")
    console.print("  exit | quit")


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
            yield from _complete_values(sorted(ALL_EXPORTS), current)
            return
        if previous in {"--view", "-v"}:
            yield from _complete_values(VIEW_CHOICES, current)
            return
        if previous == "--fps":
            return
        if previous in {"--out", "-o", "--backend"}:
            if previous == "--backend":
                yield from _complete_values(["auto", "rosbags", "sqlite"], current)
            else:
                yield from _complete_paths(current)
            return
        if current.startswith("-"):
            yield from _complete_values(OPTIONS_BY_COMMAND.get(command, []), current)
            return
        if command in {"open", "scan"}:
            yield from _complete_paths(current)
            return
        if command in {"export", "dur"}:
            yield from _complete_values(self._topic_names(), current)

    def _topic_names(self) -> list[str]:
        return sorted(topic.name for topic in self.session.topics)


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


def _complete_values(values: Iterable[str], current: str) -> Iterable[Completion]:
    for value in values:
        if value.startswith(current):
            yield Completion(value, start_position=-len(current))


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
