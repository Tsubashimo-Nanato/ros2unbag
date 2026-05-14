from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Annotated

import typer

from ros2unbag.cli.render import (
    console,
    render_export_result,
    render_export_results,
    render_inspect_results,
    render_scan_view,
    render_topic_duration,
    render_warnings,
)
from ros2unbag.cli.progress import progress_task
from ros2unbag.core.manifest import write_manifest, write_topics_csv
from ros2unbag.core.session import (
    ALL_EXPORTS,
    FUTURE_EXPORTS,
    Session,
    validate_export_format,
)

UNINSTALL_PACKAGES = (
    "ros2unbag",
    "rosbag-inspector",
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
    name="ros2unbag",
    help="Offline ROS bag inspection and export tool.",
    no_args_is_help=False,
)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Start the interactive shell when no command is provided."""
    if ctx.invoked_subcommand is None:
        from ros2unbag.cli.repl import run_repl

        run_repl()
        raise typer.Exit()


def _open_session_with_progress(session: Session, bag_path: Path) -> None:
    with progress_task("Opening bag", None) as advance:
        session.open_bag(bag_path)
        advance()


@app.command()
def scan(
    bag_path: Annotated[Path, typer.Argument(help="Bag folder, .db3 file, or supported bag file.")],
    out: Annotated[Path | None, typer.Option("--out", "-o", help="Optional output directory.")] = None,
    view: Annotated[
        str,
        typer.Option("--view", "-v", help="Output view: table, tree, or nav."),
    ] = "table",
    backend: Annotated[
        str, typer.Option(help="Backend: auto, rosbags, or sqlite.")
    ] = "auto",
) -> None:
    """Scan a bag and list topics, timestamps, categories, and export hints."""
    session = Session(backend=backend)
    try:
        _open_session_with_progress(session, bag_path)
        manifest = session.scan(progress_factory=progress_task)
        render_scan_view(manifest.topics, view=view)
        render_warnings(manifest.warnings)
        if out is not None:
            out.mkdir(parents=True, exist_ok=True)
            manifest_path = write_manifest(manifest, out / "manifest.json")
            topics_path = write_topics_csv(manifest.topics, out / "topics.csv")
            console.print(f"Wrote [bold]{manifest_path}[/bold]")
            console.print(f"Wrote [bold]{topics_path}[/bold]")
    finally:
        session.close()


@app.command()
def export(
    bag_path: Annotated[Path, typer.Argument(help="Bag folder, .db3 file, or supported bag file.")],
    topic: Annotated[str, typer.Option("--topic", "-t", help="Topic to export.")],
    export_format: Annotated[
        str,
        typer.Option("--format", "-f", help="csv, jsonl, raw, png, jpg, mp4, parquet, sqlite."),
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


@app.command("inspect")
def inspect_command(
    bag_path: Annotated[Path, typer.Argument(help="Bag folder, .db3 file, or supported bag file.")],
    time: Annotated[
        float,
        typer.Option("--time", help="Seconds after bag start, unless --absolute-ns is set."),
    ],
    absolute_ns: Annotated[
        bool,
        typer.Option("--absolute-ns", help="Interpret --time as an absolute nanosecond timestamp."),
    ] = False,
    backend: Annotated[
        str, typer.Option(help="Backend: auto, rosbags, or sqlite.")
    ] = "auto",
) -> None:
    """Show nearest message from every topic at a requested timestamp."""
    session = Session(backend=backend)
    try:
        _open_session_with_progress(session, bag_path)
        target_ns, results, warnings = session.inspect_time(
            time,
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


@app.command("uninstall")
def uninstall_command(
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Run the uninstall command without printing only."),
    ] = False,
    print_only: Annotated[
        bool,
        typer.Option("--print-only", help="Only print the pip uninstall command."),
    ] = False,
) -> None:
    """Print or run the clean package and dependency uninstall command."""
    display = "py -m pip uninstall " + " ".join(UNINSTALL_PACKAGES)
    if print_only or not yes:
        console.print("Clean uninstall command:")
        console.print(f"[bold]{display}[/bold]", soft_wrap=False)
        console.print("This removes ros2unbag, the old rosbag-inspector package, and runtime dependencies.")
        console.print("Run [bold]ros2unbag uninstall --yes[/bold] to execute it.")
        return

    exec_command = [sys.executable, "-m", "pip", "uninstall", "-y", *UNINSTALL_PACKAGES]
    console.print("Uninstalling ros2unbag, previous package names, and dependencies...")
    os.execv(sys.executable, exec_command)


if __name__ == "__main__":
    app()

