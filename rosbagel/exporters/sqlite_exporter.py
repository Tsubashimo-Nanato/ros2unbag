from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from rosbagel.core.decoder import message_to_plain
from rosbagel.core.manifest import sanitize_topic_name
from rosbagel.core.models import ExportResult
from rosbagel.core.point_cloud import iter_point_cloud_rows, point_cloud_field_names
from rosbagel.core.progress import ProgressCallback
from rosbagel.core.progress import advance_progress
from rosbagel.exporters.csv_exporter import _topic_msgtype
from rosbagel.exporters.tabular import collect_tabular_topic_data


def export_topic_sqlite(
    reader: object,
    topic: str,
    out_dir: str | Path,
    *,
    bag_start_timestamp_ns: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> ExportResult:
    """Export one topic into a reusable SQLite session database."""
    if _topic_msgtype(reader, topic) == "sensor_msgs/msg/PointCloud2":
        return _export_point_cloud_sqlite_streaming(
            reader,
            topic,
            out_dir,
            bag_start_timestamp_ns=bag_start_timestamp_ns,
            progress_callback=progress_callback,
        )

    output_dir = Path(out_dir) / "sqlite"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "session.sqlite"
    data = collect_tabular_topic_data(
        reader,
        topic,
        bag_start_timestamp_ns=bag_start_timestamp_ns,
        progress_callback=progress_callback,
    )
    table_name = _topic_table_name(topic)
    msgtype = _first_msgtype(reader, topic) or ""

    connection = sqlite3.connect(output_path)
    try:
        _ensure_session_tables(connection)
        _upsert_topic(
            connection,
            topic=topic,
            msgtype=msgtype,
            message_count=data.source_message_count,
            first_timestamp_ns=data.first_timestamp_ns,
            last_timestamp_ns=data.last_timestamp_ns,
        )
        _replace_topic_table(
            connection,
            table_name=table_name,
            fieldnames=data.fieldnames,
            rows=data.rows,
        )
        _replace_messages_for_topic(
            connection,
            topic=topic,
            msgtype=msgtype,
            rows=data.rows,
        )
        _insert_export(
            connection,
            topic=topic,
            table_name=table_name,
            output_path=output_path,
            message_count=data.source_message_count,
            warnings=data.warnings,
        )
        connection.commit()
    finally:
        connection.close()

    return ExportResult(
        topic=topic,
        format="sqlite",
        output_path=str(output_path),
        message_count=data.source_message_count,
        first_timestamp_ns=data.first_timestamp_ns,
        last_timestamp_ns=data.last_timestamp_ns,
        warnings=data.warnings,
    )


def _export_point_cloud_sqlite_streaming(
    reader: object,
    topic: str,
    out_dir: str | Path,
    *,
    bag_start_timestamp_ns: int | None,
    progress_callback: ProgressCallback | None,
) -> ExportResult:
    output_dir = Path(out_dir) / "sqlite"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "session.sqlite"
    table_name = _topic_table_name(topic)
    msgtype = _first_msgtype(reader, topic) or "sensor_msgs/msg/PointCloud2"
    source_count = 0
    point_row_count = 0
    first_timestamp: int | None = None
    last_timestamp: int | None = None
    warnings: list[str] = []
    fieldnames: list[str] | None = None
    topic_rows: list[dict[str, Any]] = []
    message_rows: list[tuple[Any, ...]] = []
    batch_size = 10_000

    connection = sqlite3.connect(output_path)
    try:
        _ensure_session_tables(connection)
        connection.execute("delete from messages where topic = ?", (topic,))
        connection.execute(f"drop table if exists {_quote_identifier(table_name)}")

        def ensure_table(decoded: object) -> None:
            nonlocal fieldnames
            if fieldnames is not None:
                return
            fieldnames = [
                "timestamp_ns",
                "timestamp_sec_from_start",
                "topic",
                *point_cloud_field_names(decoded),
            ]
            column_sql = ", ".join(
                f"{_quote_identifier(field)} {_point_cloud_sqlite_type(field)}"
                for field in fieldnames
            )
            connection.execute(f"create table {_quote_identifier(table_name)} ({column_sql})")
            connection.execute(
                f"create index {_quote_identifier(f'idx_{table_name}_timestamp_ns')} "
                f"on {_quote_identifier(table_name)} ({_quote_identifier('timestamp_ns')})"
            )

        def flush() -> None:
            nonlocal topic_rows, message_rows
            if fieldnames and topic_rows:
                placeholders = ", ".join("?" for _ in fieldnames)
                insert_sql = (
                    f"insert into {_quote_identifier(table_name)} "
                    f"({', '.join(_quote_identifier(field) for field in fieldnames)}) "
                    f"values ({placeholders})"
                )
                connection.executemany(
                    insert_sql,
                    [tuple(_sqlite_value(row.get(field)) for field in fieldnames) for row in topic_rows],
                )
                topic_rows = []
            if message_rows:
                connection.executemany(
                    """
                    insert into messages(topic, msgtype, timestamp_ns, timestamp_sec_from_start, row_index, data_json)
                    values (?, ?, ?, ?, ?, ?)
                    """,
                    message_rows,
                )
                message_rows = []

        for record in reader.iter_messages(topics=[topic]):
            source_count += 1
            first_timestamp = record.timestamp_ns if first_timestamp is None else first_timestamp
            last_timestamp = record.timestamp_ns
            if record.decoded is None:
                warnings.append("Message was not decoded; SQLite contains decoded point rows only.")
                advance_progress(progress_callback)
                continue
            ensure_table(record.decoded)
            base_row = {
                "timestamp_ns": record.timestamp_ns,
                "timestamp_sec_from_start": _sec_from_start(
                    record.timestamp_ns, bag_start_timestamp_ns
                ),
                "topic": record.topic,
            }
            for point_row in iter_point_cloud_rows(record.decoded):
                row = dict(base_row)
                row.update(point_row)
                row_index = point_row_count
                topic_rows.append(row)
                message_rows.append(
                    (
                        topic,
                        msgtype,
                        row.get("timestamp_ns"),
                        row.get("timestamp_sec_from_start"),
                        row_index,
                        json.dumps(row, sort_keys=True, separators=(",", ":"), default=str),
                    )
                )
                point_row_count += 1
                if len(topic_rows) >= batch_size:
                    flush()
            advance_progress(progress_callback)
        if fieldnames is None:
            fieldnames = ["timestamp_ns", "timestamp_sec_from_start", "topic"]
            connection.execute(
                f"create table {_quote_identifier(table_name)} "
                '("timestamp_ns" integer, "timestamp_sec_from_start" real, "topic" text)'
            )
        flush()
        if source_count != point_row_count:
            warnings.append(
                f"PointCloud2 SQLite expands {source_count} source messages into {point_row_count} point rows."
            )
        _upsert_topic(
            connection,
            topic=topic,
            msgtype=msgtype,
            message_count=source_count,
            first_timestamp_ns=first_timestamp,
            last_timestamp_ns=last_timestamp,
        )
        _insert_export(
            connection,
            topic=topic,
            table_name=table_name,
            output_path=output_path,
            message_count=source_count,
            warnings=warnings,
        )
        connection.commit()
    finally:
        connection.close()

    return ExportResult(
        topic=topic,
        format="sqlite",
        output_path=str(output_path),
        message_count=source_count,
        first_timestamp_ns=first_timestamp,
        last_timestamp_ns=last_timestamp,
        warnings=sorted(set(warnings)),
    )


def _point_cloud_sqlite_type(fieldname: str) -> str:
    if fieldname in {"timestamp_ns", "point_index", "cloud_row", "cloud_col"}:
        return "integer"
    if fieldname == "timestamp_sec_from_start":
        return "real"
    return "real"


def _sec_from_start(timestamp_ns: int, bag_start_timestamp_ns: int | None) -> float | None:
    if bag_start_timestamp_ns is None:
        return None
    return (timestamp_ns - bag_start_timestamp_ns) / 1e9


def _ensure_session_tables(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        create table if not exists topics (
            topic text primary key,
            msgtype text not null,
            message_count integer not null,
            first_timestamp_ns integer,
            last_timestamp_ns integer
        )
        """
    )
    connection.execute(
        """
        create table if not exists messages (
            id integer primary key autoincrement,
            topic text not null,
            msgtype text not null,
            timestamp_ns integer,
            timestamp_sec_from_start real,
            row_index integer not null,
            data_json text not null
        )
        """
    )
    connection.execute(
        "create index if not exists idx_messages_topic_timestamp on messages(topic, timestamp_ns)"
    )
    connection.execute(
        """
        create table if not exists exports (
            id integer primary key autoincrement,
            topic text not null,
            format text not null,
            output_path text not null,
            table_name text,
            message_count integer not null,
            warnings_json text not null,
            created_at text not null default current_timestamp
        )
        """
    )


def _upsert_topic(
    connection: sqlite3.Connection,
    *,
    topic: str,
    msgtype: str,
    message_count: int,
    first_timestamp_ns: int | None,
    last_timestamp_ns: int | None,
) -> None:
    connection.execute(
        """
        insert into topics(topic, msgtype, message_count, first_timestamp_ns, last_timestamp_ns)
        values (?, ?, ?, ?, ?)
        on conflict(topic) do update set
            msgtype = excluded.msgtype,
            message_count = excluded.message_count,
            first_timestamp_ns = excluded.first_timestamp_ns,
            last_timestamp_ns = excluded.last_timestamp_ns
        """,
        (topic, msgtype, message_count, first_timestamp_ns, last_timestamp_ns),
    )


def _replace_topic_table(
    connection: sqlite3.Connection,
    *,
    table_name: str,
    fieldnames: list[str],
    rows: list[dict[str, Any]],
) -> None:
    quoted = _quote_identifier(table_name)
    connection.execute(f"drop table if exists {quoted}")
    columns = [_quote_identifier(field) for field in fieldnames]
    column_sql = ", ".join(
        f"{_quote_identifier(field)} {_sqlite_type(field, rows)}"
        for field in fieldnames
    )
    connection.execute(f"create table {quoted} ({column_sql})")
    if rows:
        placeholders = ", ".join("?" for _ in fieldnames)
        insert_sql = f"insert into {quoted} ({', '.join(columns)}) values ({placeholders})"
        connection.executemany(
            insert_sql,
            [
                tuple(_sqlite_value(row.get(field)) for field in fieldnames)
                for row in rows
            ],
        )
    if "timestamp_ns" in fieldnames:
        index_name = _quote_identifier(f"idx_{table_name}_timestamp_ns")
        connection.execute(f"create index {index_name} on {quoted} ({_quote_identifier('timestamp_ns')})")


def _replace_messages_for_topic(
    connection: sqlite3.Connection,
    *,
    topic: str,
    msgtype: str,
    rows: list[dict[str, Any]],
) -> None:
    connection.execute("delete from messages where topic = ?", (topic,))
    connection.executemany(
        """
        insert into messages(topic, msgtype, timestamp_ns, timestamp_sec_from_start, row_index, data_json)
        values (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                topic,
                msgtype,
                row.get("timestamp_ns"),
                row.get("timestamp_sec_from_start"),
                index,
                json.dumps(row, sort_keys=True, separators=(",", ":"), default=str),
            )
            for index, row in enumerate(rows)
        ],
    )


def _insert_export(
    connection: sqlite3.Connection,
    *,
    topic: str,
    table_name: str,
    output_path: Path,
    message_count: int,
    warnings: list[str],
) -> None:
    connection.execute(
        """
        insert into exports(topic, format, output_path, table_name, message_count, warnings_json)
        values (?, 'sqlite', ?, ?, ?, ?)
        """,
        (
            topic,
            str(output_path),
            table_name,
            message_count,
            json.dumps(warnings, sort_keys=True),
        ),
    )


def _first_msgtype(reader: object, topic: str) -> str | None:
    for item in getattr(reader, "get_topics", lambda: [])():
        if getattr(item, "name", None) == topic:
            return str(getattr(item, "msgtype", ""))
    for record in reader.iter_messages(topics=[topic]):
        return str(record.msgtype)
    return None


def _topic_table_name(topic: str) -> str:
    return "topic__" + sanitize_topic_name(topic)


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _sqlite_type(fieldname: str, rows: list[dict[str, Any]]) -> str:
    if fieldname in {"timestamp_ns", "point_index", "row", "col", "raw_byte_length"}:
        return "integer"
    if fieldname == "timestamp_sec_from_start":
        return "real"
    values = [row.get(fieldname) for row in rows if row.get(fieldname) is not None]
    if values and all(isinstance(value, bool) for value in values):
        return "integer"
    if values and all(isinstance(value, int) and not isinstance(value, bool) for value in values):
        return "integer"
    if values and all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values):
        return "real"
    return "text"


def _sqlite_value(value: Any) -> Any:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (str, int, float)) or value is None:
        return value
    return json.dumps(message_to_plain(value), sort_keys=True, separators=(",", ":"))

