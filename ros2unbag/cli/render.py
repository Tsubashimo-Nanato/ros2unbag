from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from rich.console import Console
from rich.markup import escape
from rich.table import Table
from rich.tree import Tree

from ros2unbag.core.models import ExportResult, ExportSelection, TopicDuration, TopicInfo
from ros2unbag.core.sync import InspectResult
from ros2unbag.core.topic_tree import (
    TopicTreeNode,
    build_topic_tree,
    format_topic_compact,
    topic_leaf_name,
    topic_parent_path,
)

console = Console()


def render_scan_view(topics: list[TopicInfo], *, view: str) -> None:
    normalized = view.lower()
    if normalized == "table":
        render_scan_table(topics)
        return
    if normalized == "tree":
        render_topic_tree(topics)
        return
    if normalized in {"nav", "browse", "interactive"}:
        run_topic_navigator(topics)
        return
    raise ValueError("scan --view must be one of: table, tree, nav")


def render_scan_table(topics: list[TopicInfo]) -> None:
    width = max(72, min(console.size.width - 2, 180))
    columns = _scan_table_columns(width)
    console.print("ROS Bag Topics", soft_wrap=False)
    header = "  ".join(label.ljust(size) for label, size, _getter in columns)
    console.print(header, soft_wrap=False)
    console.print("-" * len(header), soft_wrap=False)
    for topic in topics:
        cells = [
            _fit_cell(getter(topic), size).ljust(size)
            for _label, size, getter in columns
        ]
        console.print("  ".join(cells), soft_wrap=False)


ScanColumn = tuple[str, int, Callable[[TopicInfo], str]]


def _scan_table_columns(width: int) -> list[ScanColumn]:
    if width >= 140:
        return [
            ("Topic", 20, lambda topic: topic_leaf_name(topic.name)),
            ("Path", 34, lambda topic: topic_parent_path(topic.name)),
            ("Count", 6, lambda topic: str(topic.message_count)),
            ("Dur s", 9, _duration_cell),
            ("Category", 14, lambda topic: topic.category),
            ("Type", 30, lambda topic: topic.msgtype),
            ("Exports", max(12, width - 20 - 34 - 6 - 9 - 14 - 30 - 12), _exports_cell),
        ]
    if width >= 110:
        type_width = max(20, width - 20 - 36 - 6 - 9 - 14 - 10)
        return [
            ("Topic", 20, lambda topic: topic_leaf_name(topic.name)),
            ("Path", 36, lambda topic: topic_parent_path(topic.name)),
            ("Count", 6, lambda topic: str(topic.message_count)),
            ("Dur s", 9, _duration_cell),
            ("Category", 14, lambda topic: topic.category),
            ("Type", type_width, lambda topic: topic.msgtype),
        ]
    path_width = max(18, width - 18 - 6 - 9 - 13 - 8)
    return [
        ("Topic", 18, lambda topic: topic_leaf_name(topic.name)),
        ("Path", path_width, lambda topic: topic_parent_path(topic.name)),
        ("Count", 6, lambda topic: str(topic.message_count)),
        ("Dur s", 9, _duration_cell),
        ("Category", 13, lambda topic: topic.category),
    ]


def _duration_cell(topic: TopicInfo) -> str:
    return "" if topic.duration_sec is None else f"{topic.duration_sec:.3f}"


def _exports_cell(topic: TopicInfo) -> str:
    return ", ".join(topic.suggested_exports)


def _fit_cell(value: object, width: int) -> str:
    text = str(value)
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    return text[: width - 3] + "..."


def render_topic_tree(topics: list[TopicInfo]) -> None:
    root = build_topic_tree(topics)
    tree = Tree(f"[cyan]/[/cyan]  [dim]({root.topic_count} topics)[/dim]")
    _add_tree_children(tree, root)
    console.print(tree)


def _add_tree_children(parent_tree: Tree, node: TopicTreeNode) -> None:
    for name in sorted(node.children):
        child = node.children[name]
        if child.children:
            label = (
                f"[blue]{escape(name)}/[/blue]  "
                f"[cyan]{escape(child.path)}[/cyan]  "
                f"[dim]({child.topic_count} topics)[/dim]"
            )
            branch = parent_tree.add(label)
            if child.topic is not None:
                branch.add(
                    f"[bold green]{escape(child.name)}[/bold green]  "
                    f"[cyan]{escape(child.path)}[/cyan]  "
                    f"[dim]{escape(format_topic_compact(child.topic))}[/dim]"
                )
            _add_tree_children(branch, child)
        elif child.topic is not None:
            parent_tree.add(
                f"[bold green]{escape(name)}[/bold green]  "
                f"[cyan]{escape(child.topic.name)}[/cyan]  "
                f"[dim]{escape(format_topic_compact(child.topic))}[/dim]"
            )


def run_topic_navigator(topics: list[TopicInfo]) -> None:
    root = build_topic_tree(topics)
    stack: list[TopicTreeNode] = [root]
    while True:
        node = stack[-1]
        console.rule(f"[bold]Topic Browser[/bold] [cyan]{escape(node.path)}[/cyan]")
        entries = [node.children[name] for name in sorted(node.children)]
        if not entries:
            console.print("[dim]No child topics here.[/dim]")
        for index, child in enumerate(entries, start=1):
            if child.children:
                suffix = f"/ [cyan]{escape(child.path)}[/cyan] [dim]({child.topic_count} topics)[/dim]"
            else:
                suffix = (
                    f"  [cyan]{escape(child.topic.name)}[/cyan] "
                    f"[dim]{escape(format_topic_compact(child.topic))}[/dim]"
                    if child.topic
                    else ""
                )
            console.print(f"[bold]{index:>2}[/bold]  [green]{escape(child.name)}[/green]{suffix}")

        console.print("[dim]Enter a number to open, b/back to go back, q/quit to exit.[/dim]")
        choice = console.input("> ").strip().lower()
        if choice in {"q", "quit", "exit"}:
            return
        if choice in {"b", "back", ".."}:
            if len(stack) > 1:
                stack.pop()
            continue
        if not choice.isdigit():
            console.print("[yellow]Please enter a number, b, or q.[/yellow]")
            continue
        selection = int(choice)
        if selection < 1 or selection > len(entries):
            console.print("[yellow]That number is not in the current list.[/yellow]")
            continue
        selected = entries[selection - 1]
        if selected.children:
            stack.append(selected)
            continue
        if selected.topic is not None:
            render_topic_detail(selected.topic)
            console.input("[dim]Press Enter to go back.[/dim]")


def render_topic_detail(topic: TopicInfo) -> None:
    console.print(f"[bold green]{escape(topic_leaf_name(topic.name))}[/bold green]")
    console.print(f"  path: [cyan]{escape(topic.name)}[/cyan]")
    console.print(f"  type: {topic.msgtype}")
    console.print(f"  serialization: {topic.serialization_format or ''}")
    console.print(f"  count: {topic.message_count}")
    console.print(f"  first ns: {topic.first_timestamp_ns or ''}")
    console.print(f"  last ns: {topic.last_timestamp_ns or ''}")
    console.print(
        "  duration: "
        + ("" if topic.duration_sec is None else f"{topic.duration_sec:.6f}s")
    )
    console.print(f"  category: {topic.category}")
    console.print(f"  suggested exports: {', '.join(topic.suggested_exports)}")


def render_opened_bag(path: str | Path, topic_count: int, *, backend: str) -> None:
    console.print(
        "[green]Opened bag[/green] "
        f"[cyan]{escape(str(path))}[/cyan] "
        f"[bold]({topic_count} topics, backend={escape(backend)})[/bold]",
        overflow="fold",
    )


def render_topic_duration(duration: TopicDuration) -> None:
    table = Table(title="Topic Duration")
    table.add_column("Field", no_wrap=True)
    table.add_column("Value", overflow="fold")
    rows = [
        ("topic", duration.topic),
        ("type", duration.msgtype),
        ("message_count", str(duration.message_count)),
        ("first_timestamp_ns", _optional_int(duration.first_timestamp_ns)),
        ("last_timestamp_ns", _optional_int(duration.last_timestamp_ns)),
        ("topic_duration_sec", _optional_float(duration.topic_duration_sec)),
        ("bag_start_timestamp_ns", _optional_int(duration.bag_start_timestamp_ns)),
        ("bag_end_timestamp_ns", _optional_int(duration.bag_end_timestamp_ns)),
        ("bag_duration_sec", _optional_float(duration.bag_duration_sec)),
        ("start_offset_sec", _optional_float(duration.start_offset_sec)),
        ("end_gap_sec", _optional_float(duration.end_gap_sec)),
    ]
    for field, value in rows:
        table.add_row(field, value)
    console.print(table)


def _optional_int(value: int | None) -> str:
    return "" if value is None else str(value)


def _optional_float(value: float | None) -> str:
    return "" if value is None else f"{value:.6f}"


def render_export_result(result: ExportResult) -> None:
    render_export_results([result])


def render_export_results(results: list[ExportResult]) -> None:
    table = Table(title="Exports")
    table.add_column("Topic", overflow="fold")
    table.add_column("Format")
    table.add_column("Messages", justify="right")
    table.add_column("Output", overflow="fold")
    for result in results:
        table.add_row(
            result.topic,
            result.format,
            str(result.message_count),
            result.output_path,
        )
    console.print(table)
    for result in results:
        for warning in result.warnings:
            console.print(f"[yellow]Warning:[/yellow] {result.topic}: {warning}")


def render_export_plan(selections: list[ExportSelection]) -> None:
    table = Table(title="Selected Exports")
    table.add_column("#", justify="right", no_wrap=True)
    table.add_column("Topic", overflow="fold")
    table.add_column("Format", no_wrap=True)
    table.add_column("Out", overflow="fold")
    table.add_column("FPS", justify="right")
    for index, selection in enumerate(selections, start=1):
        table.add_row(
            str(index),
            selection.topic,
            selection.format,
            selection.out_dir,
            "" if selection.format != "mp4" else f"{selection.fps:g}",
        )
    console.print(table)


def render_inspect_results(
    target_ns: int, results: list[InspectResult], warnings: list[str]
) -> None:
    console.print(f"Target timestamp: [bold]{target_ns}[/bold] ns")
    table = Table(title="Nearest Messages")
    table.add_column("Topic", overflow="fold")
    table.add_column("Type", overflow="fold")
    table.add_column("Nearest ns", justify="right")
    table.add_column("Delta ms", justify="right")
    table.add_column("Summary", overflow="fold")
    for result in results:
        table.add_row(
            result.topic,
            result.msgtype,
            "" if result.nearest_timestamp_ns is None else str(result.nearest_timestamp_ns),
            "" if result.delta_ms is None else f"{result.delta_ms:.3f}",
            str(result.summary.get("summary", "")),
        )
    console.print(table)
    render_warnings(warnings)


def render_warnings(warnings: list[str]) -> None:
    for warning in warnings:
        console.print(f"[yellow]Warning:[/yellow] {warning}")

