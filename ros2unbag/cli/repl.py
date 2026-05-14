from __future__ import annotations

import os
from pathlib import Path
import shlex
import sys
from typing import Callable, Iterable

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.history import FileHistory
from rich.prompt import Confirm

from ros2unbag.cli.progress import progress_task
from ros2unbag.cli.render import (
    console,
    render_export_plan,
    render_export_result,
    render_export_results,
    render_inspect_results,
    render_opened_bag,
    render_scan_view,
    render_topic_duration,
    render_warnings,
)
from ros2unbag.core.manifest import write_manifest, write_topics_csv
from ros2unbag.core.models import ExportSelection
from ros2unbag.core.session import ALL_EXPORTS, Session, compatible_export_formats

COMMANDS = [
    "open",
    "close",
    "scan",
    "topics",
    "export",
    "export-select",
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
    "scan": ["-v", "--view", "-o", "--out", "--backend"],
    "topics": ["-v", "--view"],
    "export": ["--topic", "-t", "--format", "-f", "--out", "-o", "--fps"],
    "export-select": ["--topic", "-t", "--format", "-f", "--out", "-o", "--fps"],
    "export-all": ["--out", "-o"],
    "inspect": ["--time", "--dur", "--absolute-ns"],
    "dur": [],
}

VIEW_CHOICES = ["table", "tree", "nav"]
BACKEND_CHOICES = ["auto", "rosbags", "sqlite"]
VALUE_OPTIONS = {
    "--backend",
    "--format",
    "-f",
    "--fps",
    "--out",
    "-o",
    "--time",
    "--dur",
    "--topic",
    "-t",
    "--view",
    "-v",
}
FLAG_OPTIONS = {"--absolute-ns"}


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
        if command == "export-select":
            _handle_export_select(session, args)
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
    except KeyboardInterrupt:
        console.print("[yellow]Interrupted.[/yellow] Current action stopped; shell is still open.")
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
    with progress_task("Opening bag", None) as advance:
        topics = session.open_bag(positionals[0], backend=backend)
        advance()
    render_opened_bag(session.bag_path or positionals[0], len(topics), backend=session.backend)
    render_warnings(list(getattr(session.reader, "warnings", [])) if session.reader else [])


def _handle_scan(session: Session, args: list[str]) -> None:
    positionals, options = _parse_args(args)
    if positionals:
        backend = _option(options, "--backend") or session.backend
        with progress_task("Opening bag", None) as advance:
            session.open_bag(positionals[0], backend=backend)
            advance()
    manifest = session.scan(progress_factory=progress_task)
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
    result = session.export_topic(topic, fmt, out, fps=fps, progress_factory=progress_task)
    render_export_result(result)


def _handle_export_select(session: Session, args: list[str]) -> None:
    run_export_select(session, initial_args=args)


def run_export_select(
    session: Session,
    *,
    initial_args: list[str] | None = None,
    default_out: str | Path | None = None,
) -> None:
    session.list_topics()
    selections: list[ExportSelection] = []
    if initial_args:
        selections.append(_selection_from_args(session, initial_args, default_out=default_out))

    console.print("[bold]Selected export mode[/bold]")
    console.print(
        "Enter lines like "
        "[cyan]TOPIC --format csv --out .\\export[/cyan]. "
        "Type [bold]export-all[/bold] to review and run, or [bold]cancel[/bold] to return."
    )

    prompt = _selection_prompt(session)
    while True:
        try:
            line = prompt("select> ")
        except KeyboardInterrupt:
            console.print("[yellow]Selection input interrupted.[/yellow] Returning to shell.")
            return
        except EOFError:
            return

        stripped = line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if lowered in {"cancel", "q", "quit", "exit"}:
            console.print("Selected export cancelled.")
            return
        if lowered in {"export-all", "done", "run"}:
            if not selections:
                console.print("[yellow]No topics have been selected yet.[/yellow]")
                continue
            render_export_plan(selections)
            if not Confirm.ask("Export these selected topics?", default=False, console=console):
                console.print("Selected export cancelled.")
                return
            results = session.export_selected(selections, progress_factory=progress_task)
            render_export_results(results)
            return

        try:
            selection = _selection_from_args(
                session,
                split_repl_line(stripped),
                default_out=default_out,
            )
        except Exception as exc:
            console.print(f"[red]Selection error:[/red] {exc}")
            continue
        selections.append(selection)
        console.print(
            "[green]Queued[/green] "
            f"[cyan]{selection.topic}[/cyan] as [bold]{selection.format}[/bold] "
            f"to [cyan]{selection.out_dir}[/cyan]",
            overflow="fold",
        )


def _selection_prompt(session: Session) -> Callable[[str], str]:
    if not sys.stdin.isatty():
        return input
    prompt_session = PromptSession(
        history=FileHistory(".ros2unbag_history"),
        completer=ExportSelectCompleter(session),
        complete_while_typing=False,
    )
    return prompt_session.prompt


def _selection_from_args(
    session: Session,
    args: list[str],
    *,
    default_out: str | Path | None = None,
) -> ExportSelection:
    positionals, options = _parse_args(args)
    topic = _option(options, "--topic", "-t") or (positionals[0] if positionals else None)
    fmt = _option(options, "--format", "-f")
    out = _option(options, "--out", "-o") or (str(default_out) if default_out is not None else None)
    fps = float(_option(options, "--fps") or 30.0)
    if topic is None or fmt is None or out is None:
        raise ValueError("Usage: TOPIC --format FORMAT --out OUT_DIR [--fps FPS]")
    return session.prepare_export_selection(topic, fmt, out, fps=fps)


def _handle_export_all(session: Session, args: list[str]) -> None:
    _positionals, options = _parse_args(args)
    out = _option(options, "--out", "-o")
    if out is None:
        raise ValueError("Usage: export-all --out OUT_DIR")
    manifest, results = session.export_all(out, progress_factory=progress_task)
    render_export_results(results)
    render_warnings(manifest.warnings)
    console.print(f"Wrote [bold]{Path(out) / 'manifest.json'}[/bold]")


def _handle_inspect(session: Session, args: list[str]) -> None:
    _positionals, options = _parse_args(args)
    raw_time = _option(options, "--time")
    duration_topic = _option(options, "--dur")
    if raw_time is None and duration_topic is None:
        raise ValueError("Usage: inspect --time SECONDS [--dur TOPIC]")
    if duration_topic is not None:
        render_topic_duration(session.topic_duration(duration_topic, progress_factory=progress_task))
    if raw_time is not None:
        target_ns, results, warnings = session.inspect_time(
            float(raw_time),
            absolute_ns="--absolute-ns" in options,
            progress_factory=progress_task,
        )
        render_inspect_results(target_ns, results, warnings)


def _handle_duration(session: Session, args: list[str]) -> None:
    positionals, _options = _parse_args(args)
    if not positionals:
        raise ValueError("Usage: dur TOPIC")
    render_topic_duration(session.topic_duration(positionals[0], progress_factory=progress_task))


def render_repl_help() -> None:
    console.print("Commands:")
    console.print("  open BAG_PATH [--backend auto|rosbags|sqlite]")
    console.print("  scan [BAG_PATH] [--view table|tree|nav] [--out OUT_DIR]")
    console.print("  topics [--view table|tree|nav]")
    console.print("  dur TOPIC")
    console.print("  inspect --time SECONDS [--dur TOPIC] [--absolute-ns]")
    console.print("  export TOPIC --format csv|parquet|sqlite|png|jpg|mp4|jsonl|raw --out OUT_DIR [--fps FPS]")
    console.print("  export-select")
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
            else:
                yield from _complete_option_values(_available_options(command, args), current)
            return
        if command == "topics":
            if not positionals and not options and not current:
                yield from _complete_option_values(["-v"], current)
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

