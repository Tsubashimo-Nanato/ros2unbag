from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ros2_unbag.core.decoder import message_to_plain
from ros2_unbag.core.manifest import sanitize_topic_name
from ros2_unbag.core.models import ExportResult
from ros2_unbag.exporters.tabular import collect_tabular_topic_data


def export_topic_sqlite(
    reader: object,
    topic: str,
    out_dir: str | Path,
    *,
    bag_start_timestamp_ns: int | None = None,
) -> ExportResult:
    """Export one topic into a reusable SQLite session database."""
    output_dir = Path(out_dir) / "sqlite"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "session.sqlite"
    data = collect_tabular_topic_data(
        reader,
        topic,
        bag_start_timestamp_ns=bag_start_timestamp_ns,
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
