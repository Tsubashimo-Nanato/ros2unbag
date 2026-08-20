from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from typing import Annotated

import typer
from rich.prompt import Confirm

from rosbagel.cli.parsing import parse_inspect_time
from rosbagel.cli.render import (
    console,
    render_export_result,
    render_export_results,
    render_inspect_results,
    render_opened_bag,
    render_scan_view,
    render_topic_duration,
    render_warnings,
)
from rosbagel.cli.progress import progress_task
from rosbagel.cli.upgrade import UPGRADE_SOURCES, build_upgrade_plan, run_upgrade
from rosbagel.core.manifest import write_manifest, write_topics_csv
from rosbagel.core.session import (
    ALL_EXPORTS,
    FUTURE_EXPORTS,
    Session,
    validate_export_format,
)

PACKAGE_NAMES = (
    "ROSBagel",
    "ros2unbag",
    "rosbag-inspector",
)

DEPENDENCY_PACKAGES = (
    "rosbags",
    "numpy",
    "pandas",
    "pyarrow",
    "opencv-python",
    "pillow",
    # Historical runtime dependency removed in 1.3.0; kept for clean uninstall.
    "tqdm",
    "typer",
    "rich",
    "prompt-toolkit",
    "PySide6",
    "PySide6-Addons",
    "PySide6-Essentials",
    "shiboken6",
    "vispy",
    "PyOpenGL",
    "apsw",
    "lz4",
    "ruamel.yaml",
    "zstandard",
    "typing-extensions",
    "click",
    "shellingham",
    "annotated-doc",
    "markdown-it-py",
    "mdurl",
    "pygments",
    "colorama",
    "wcwidth",
)

app = typer.Typer(
    name="bagel",
    help="Offline ROS bag inspection and export tool.",
    no_args_is_help=False,
)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Start the interactive shell when no command is provided."""
    if ctx.invoked_subcommand is None:
        from rosbagel.cli.repl import run_repl

        run_repl()
        raise typer.Exit()


def _open_session_with_progress(session: Session, bag_path: Path) -> int:
    if not bag_path.exists():
        raise typer.BadParameter(f"Bag path does not exist: {bag_path}")

    try:
        with progress_task("Opening bag", None) as advance:
            topics = session.open_bag(bag_path)
            advance()
    except (OSError, RuntimeError, ValueError) as exc:
        raise typer.BadParameter(f"Could not open bag '{bag_path}': {exc}") from exc
    return len(topics)


@app.command()
def scan(
    bag_path: Annotated[Path, typer.Argument(help="Bag folder, .db3 file, or supported bag file.")],
    out: Annotated[Path | None, typer.Option("--out", "-o", help="Optional output directory.")] = None,
    all_topics: Annotated[
        bool,
        typer.Option(
            "--all",
            "-all",
            help="Scan all topics. This is the default behavior.",
            show_default=False,
        ),
    ] = True,
) -> None:
    """Scan a bag and list topics, timestamps, categories, and export hints."""
    _ = all_topics
    session = Session()
    try:
        _open_session_with_progress(session, bag_path)
        manifest = session.scan(progress_factory=progress_task)
        render_scan_view(manifest.topics, view="all")
        render_warnings(manifest.warnings)
        if out is not None:
            out.mkdir(parents=True, exist_ok=True)
            manifest_path = write_manifest(manifest, out / "manifest.json")
            topics_path = write_topics_csv(manifest.topics, out / "topics.csv")
            console.print(f"Wrote [bold]{manifest_path}[/bold]")
            console.print(f"Wrote [bold]{topics_path}[/bold]")
    finally:
        session.close()


@app.command("topics")
def topics_command(
    bag_path: Annotated[Path, typer.Argument(help="Bag folder, .db3 file, or supported bag file.")],
    all_topics: Annotated[
        bool,
        typer.Option("--all", "-all", help="Show the full detailed topic table."),
    ] = False,
    select: Annotated[
        bool,
        typer.Option("--select", "-s", help="Open the interactive topic path selector."),
    ] = False,
) -> None:
    """List bag topics as a tree, detailed table, or selector."""
    session = Session()
    try:
        _open_session_with_progress(session, bag_path)
        if select:
            render_scan_view(session.list_topics(), view="select")
        elif all_topics:
            manifest = session.scan(progress_factory=progress_task)
            render_scan_view(manifest.topics, view="all")
            render_warnings(manifest.warnings)
        else:
            render_scan_view(session.list_topics(), view="tree")
    finally:
        session.close()


@app.command()
def export(
    bag_path: Annotated[Path, typer.Argument(help="Bag folder, .db3 file, or supported bag file.")],
    topic: Annotated[str, typer.Option("--topic", "-t", help="Topic to export.")],
    export_format: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="csv, jsonl, raw, png, jpg, mp4, parquet, sqlite, npz, pcd, ply.",
        ),
    ],
    out: Annotated[Path, typer.Option("--out", "-o", help="Output directory.")],
    fps: Annotated[
        float,
        typer.Option("--fps", help="MP4 export FPS. ROS timestamps are written to a sidecar CSV."),
    ] = 30.0,
    backend: Annotated[
        str, typer.Option(help="Backend: auto, rosbags, or sqlite.")
    ] = "auto",
) -> None:
    """Export one topic."""
    try:
        fmt = validate_export_format(export_format)
        if fmt in FUTURE_EXPORTS:
            raise typer.BadParameter(FUTURE_EXPORTS[fmt])
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    session = Session(backend=backend)
    try:
        _open_session_with_progress(session, bag_path)
        try:
            result = session.export_topic(topic, fmt, out, fps=fps, progress_factory=progress_task)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
        render_export_result(result)
    finally:
        session.close()


@app.command("export-all")
def export_all(
    bag_path: Annotated[Path, typer.Argument(help="Bag folder, .db3 file, or supported bag file.")],
    out: Annotated[Path, typer.Option("--out", "-o", help="Output directory.")],
    backend: Annotated[
        str, typer.Option(help="Backend: auto, rosbags, or sqlite.")
    ] = "auto",
) -> None:
    """Export every topic using the best implemented default for its category."""
    session = Session(backend=backend)
    try:
        _open_session_with_progress(session, bag_path)
        manifest, results = session.export_all(out, progress_factory=progress_task)
        render_export_results(results)
        render_warnings(manifest.warnings)
        console.print(f"Wrote [bold]{Path(out) / 'manifest.json'}[/bold]")
    finally:
        session.close()


@app.command("export-select")
def export_select(
    bag_path: Annotated[Path, typer.Argument(help="Bag folder, .db3 file, or supported bag file.")],
    out: Annotated[
        Path | None,
        typer.Option("--out", "-o", help="Default output directory for selected exports."),
    ] = None,
    backend: Annotated[
        str, typer.Option(help="Backend: auto, rosbags, or sqlite.")
    ] = "auto",
) -> None:
    """Interactively queue selected topic exports, then confirm and run them."""
    from rosbagel.cli.repl import run_export_select

    session = Session(backend=backend)
    try:
        topic_count = _open_session_with_progress(session, bag_path)
        render_opened_bag(session.bag_path or bag_path, topic_count, backend=session.backend)
        run_export_select(session, default_out=out)
    finally:
        session.close()


@app.command("inspect")
def inspect_command(
    bag_path: Annotated[Path, typer.Argument(help="Bag folder, .db3 file, or supported bag file.")],
    time: Annotated[
        str | None,
        typer.Option("--time", help="Seconds after bag start, unless --absolute-ns is set."),
    ] = None,
    duration_topic: Annotated[
        str | None,
        typer.Option("--dur", help="Also show duration and bag-relative coverage for a topic."),
    ] = None,
    absolute_ns: Annotated[
        bool,
        typer.Option("--absolute-ns", help="Interpret --time as an absolute nanosecond timestamp."),
    ] = False,
    backend: Annotated[
        str, typer.Option(help="Backend: auto, rosbags, or sqlite.")
    ] = "auto",
) -> None:
    """Inspect nearest messages and optionally show topic duration."""
    if time is None and duration_topic is None:
        raise typer.BadParameter("Provide --time SECONDS, --dur TOPIC, or both.")

    try:
        inspect_time = (
            parse_inspect_time(time, absolute_ns=absolute_ns)
            if time is not None
            else None
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    session = Session(backend=backend)
    try:
        _open_session_with_progress(session, bag_path)
        if duration_topic is not None:
            render_topic_duration(session.topic_duration(duration_topic, progress_factory=progress_task))
        if inspect_time is not None:
            target_ns, results, warnings = session.inspect_time(
                inspect_time,
                absolute_ns=absolute_ns,
                progress_factory=progress_task,
            )
            render_inspect_results(target_ns, results, warnings)
    finally:
        session.close()


@app.command("dur")
def duration_command(
    bag_path: Annotated[Path, typer.Argument(help="Bag folder, .db3 file, or supported bag file.")],
    topic: Annotated[str, typer.Argument(help="Topic path or unique topic leaf name.")],
    backend: Annotated[
        str, typer.Option(help="Backend: auto, rosbags, or sqlite.")
    ] = "auto",
) -> None:
    """Show duration and bag-relative coverage for one topic."""
    session = Session(backend=backend)
    try:
        _open_session_with_progress(session, bag_path)
        render_topic_duration(session.topic_duration(topic, progress_factory=progress_task))
    finally:
        session.close()


@app.command("manifest")
def manifest_command(
    bag_path: Annotated[Path, typer.Argument(help="Bag folder, .db3 file, or supported bag file.")],
    out: Annotated[Path, typer.Option("--out", "-o", help="Manifest JSON path.")],
    backend: Annotated[
        str, typer.Option(help="Backend: auto, rosbags, or sqlite.")
    ] = "auto",
) -> None:
    """Write a manifest JSON file."""
    session = Session(backend=backend)
    try:
        _open_session_with_progress(session, bag_path)
        manifest = session.scan(progress_factory=progress_task)
        output_path = write_manifest(manifest, out)
        console.print(f"Wrote [bold]{output_path}[/bold]")
        render_warnings(manifest.warnings)
    finally:
        session.close()


@app.command("formats")
def formats_command() -> None:
    """List known export formats."""
    console.print(", ".join(sorted(ALL_EXPORTS)))


@app.command("gui")
def gui_command(
    bag_path: Annotated[
        Path | None,
        typer.Argument(help="Optional bag folder, .db3 file, or supported bag file."),
    ] = None,
) -> None:
    """Start the optional PySide6 offline timeline viewer."""
    try:
        from rosbagel.gui.timeline_viewer import run_gui
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc

    try:
        run_gui(bag_path)
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc


@app.command("uninstall")
def uninstall_command(
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Uninstall without interactive confirmation."),
    ] = False,
    dependencies: Annotated[
        bool,
        typer.Option(
            "--dependencies",
            help="Also remove ROSBagel runtime and optional GUI dependencies.",
        ),
    ] = False,
    print_only: Annotated[
        bool,
        typer.Option("--print-only", help="Only print the pip uninstall command."),
    ] = False,
) -> None:
    """Uninstall ROSBagel and optionally remove its dependencies."""
    remove_dependencies = dependencies
    if not print_only and not yes:
        if not Confirm.ask("Uninstall ROSBagel?", default=False, console=console):
            console.print("Uninstall cancelled.")
            return
        remove_dependencies = Confirm.ask(
            "Also remove all ROSBagel dependencies?",
            default=False,
            console=console,
        )

    packages = uninstall_packages(remove_dependencies=remove_dependencies)
    display = "py -m pip uninstall -y " + " ".join(packages)
    if print_only:
        console.print("Uninstall command:")
        console.print(f"[bold]{display}[/bold]", soft_wrap=False)
        if not remove_dependencies:
            console.print("Dependencies will be kept.")
        return

    scope = "ROSBagel and its dependencies" if remove_dependencies else "ROSBagel"
    console.print(f"Uninstalling {scope}...")
    exec_command = [sys.executable, "-m", "pip", "uninstall", "-y", *packages]
    completed = subprocess.run(exec_command, check=False)
    if completed.returncode != 0:
        console.print(f"[red]Uninstall failed with exit code {completed.returncode}.[/red]")
        raise typer.Exit(completed.returncode)
    console.print("Uninstall finished. The bagel command has been removed from this Python environment.")


def uninstall_packages(*, remove_dependencies: bool) -> tuple[str, ...]:
    if not remove_dependencies:
        return PACKAGE_NAMES
    return (*PACKAGE_NAMES, *DEPENDENCY_PACKAGES)


@app.command("upgrade")
def upgrade_command(
    source: Annotated[
        str,
        typer.Option(
            "--source",
            help="Upgrade source: github or pypi. GitHub is the default release source.",
        ),
    ] = "github",
    ref: Annotated[
        str | None,
        typer.Option(
            "--ref",
            help="GitHub branch/tag/commit, or exact PyPI version when --source pypi is used.",
        ),
    ] = None,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Run the upgrade command without printing only."),
    ] = False,
    print_only: Annotated[
        bool,
        typer.Option("--print-only", help="Only print the pip upgrade command."),
    ] = False,
) -> None:
    """Print or run the self-upgrade command."""
    try:
        plan = build_upgrade_plan(source=source, ref=ref)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    if print_only or not yes:
        console.print("Upgrade command:")
        console.print(f"[bold]{plan.display_command}[/bold]", soft_wrap=False)
        console.print("Run [bold]bagel upgrade --yes[/bold] to execute it.")
        console.print(f"Sources: {', '.join(UPGRADE_SOURCES)}")
        return

    console.print(f"Upgrading ROSBagel from [bold]{plan.source}[/bold]...")
    run_upgrade(plan)
    console.print("[green]Upgrade finished.[/green] Restart bagel to use the updated code.")


if __name__ == "__main__":
    app()

