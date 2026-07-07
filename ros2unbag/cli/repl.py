from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Callable

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from rich.prompt import Confirm

from ros2unbag.cli.completion import ExportSelectCompleter, Ros2UnbagCompleter
from ros2unbag.cli.parsing import flag as _flag
from ros2unbag.cli.parsing import option as _option
from ros2unbag.cli.parsing import parse_args as _parse_args
from ros2unbag.cli.parsing import parse_inspect_time
from ros2unbag.cli.parsing import split_repl_line
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
from ros2unbag.cli.upgrade import build_upgrade_plan, run_upgrade
from ros2unbag.core.manifest import write_manifest, write_topics_csv
from ros2unbag.core.models import ExportSelection
from ros2unbag.core.session import Session


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
        if command == "gui":
            _handle_gui(session, args)
            return False
        if command == "upgrade":
            _handle_upgrade(args)
            return False
        console.print(f"[red]Unknown command:[/red] {command}")
        console.print("Type [bold]help[/bold] for available commands.")
    except KeyboardInterrupt:
        console.print("[yellow]Interrupted.[/yellow] Current action stopped; shell is still open.")
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
    return False


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
        with progress_task("Opening bag", None) as advance:
            session.open_bag(positionals[0])
            advance()
    manifest = session.scan(progress_factory=progress_task)
    render_scan_view(manifest.topics, view="all")
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
    if _flag(options, "--select", "-s"):
        render_scan_view(session.list_topics(), view="select")
        return
    if _flag(options, "--all", "-all"):
        manifest = session.scan(progress_factory=progress_task)
        render_scan_view(manifest.topics, view="all")
        render_warnings(manifest.warnings)
        return
    render_scan_view(session.list_topics(), view="tree")


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
    absolute_ns = "--absolute-ns" in options
    inspect_time = (
        parse_inspect_time(raw_time, absolute_ns=absolute_ns)
        if raw_time is not None
        else None
    )
    if duration_topic is not None:
        render_topic_duration(session.topic_duration(duration_topic, progress_factory=progress_task))
    if inspect_time is not None:
        target_ns, results, warnings = session.inspect_time(
            inspect_time,
            absolute_ns=absolute_ns,
            progress_factory=progress_task,
        )
        render_inspect_results(target_ns, results, warnings)


def _handle_duration(session: Session, args: list[str]) -> None:
    positionals, _options = _parse_args(args)
    if not positionals:
        raise ValueError("Usage: dur TOPIC")
    render_topic_duration(session.topic_duration(positionals[0], progress_factory=progress_task))


def _handle_gui(session: Session, args: list[str]) -> None:
    positionals, _options = _parse_args(args)
    bag_path = Path(positionals[0]) if positionals else session.bag_path
    try:
        from ros2unbag.gui.timeline_viewer import run_gui
    except RuntimeError as exc:
        raise RuntimeError(str(exc)) from exc
    run_gui(bag_path)


def _handle_upgrade(args: list[str]) -> None:
    _positionals, options = _parse_args(args)
    source = _option(options, "--source") or "github"
    ref = _option(options, "--ref")
    plan = build_upgrade_plan(source=source, ref=ref)

    console.print("Upgrade command:")
    console.print(f"[bold]{plan.display_command}[/bold]", soft_wrap=False)
    if _flag(options, "--print-only"):
        return
    if not _flag(options, "--yes", "-y"):
        if not Confirm.ask("Run upgrade now?", default=False, console=console):
            console.print("Upgrade cancelled.")
            return

    console.print(f"Upgrading ros2unbag from [bold]{plan.source}[/bold]...")
    run_upgrade(plan)
    console.print("[green]Upgrade finished.[/green] Restart ros2unbag to use the updated code.")


def render_repl_help() -> None:
    console.print("Commands:")
    console.print("  open BAG_PATH [--backend auto|rosbags|sqlite]")
    console.print("  scan [BAG_PATH] [--all] [--out OUT_DIR]")
    console.print("  topics")
    console.print("  topics -all")
    console.print("  topics -s")
    console.print("  dur TOPIC")
    console.print("  inspect --time SECONDS [--dur TOPIC] [--absolute-ns]")
    console.print("  export TOPIC --format csv|parquet|sqlite|png|jpg|mp4|jsonl|raw|npz|pcd|ply --out OUT_DIR [--fps FPS]")
    console.print("  export-select")
    console.print("  export-all --out OUT_DIR")
    console.print("  gui [BAG_PATH]")
    console.print("  upgrade [--source github|pypi] [--ref REF] [--yes]")
    console.print("  close")
    console.print("  clear")
    console.print("  exit | quit")



