from __future__ import annotations

import dataclasses
import sqlite3
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from ros2_unbag.core.models import MessageRecord, TopicInfo
from ros2_unbag.core.session import IMPLEMENTED_EXPORTS, run_export
from ros2_unbag.exporters.parquet_exporter import export_topic_parquet
from ros2_unbag.exporters.sqlite_exporter import export_topic_sqlite


@dataclasses.dataclass
class Nested:
    value: float


@dataclasses.dataclass
class FakeMessage:
    label: str
    nested: Nested
    count: int


class FakeReader:
    def __init__(self, records: list[MessageRecord]) -> None:
        self.records = records

    def get_topics(self) -> list[TopicInfo]:
        seen: dict[str, TopicInfo] = {}
        for record in self.records:
            seen.setdefault(record.topic, TopicInfo(record.topic, record.msgtype))
        return list(seen.values())

    def iter_messages(self, topics: list[str] | None = None) -> object:
        topic_filter = set(topics or [])
        for record in self.records:
            if not topic_filter or record.topic in topic_filter:
                yield record


class Phase4ExportTests(unittest.TestCase):
    def test_parquet_export_writes_flattened_rows(self) -> None:
        topic = "/numbers"
        reader = FakeReader([_record(topic, 100, "one"), _record(topic, 200, "two")])

        with tempfile.TemporaryDirectory() as temp_dir:
            result = export_topic_parquet(
                reader,
                topic,
                Path(temp_dir),
                bag_start_timestamp_ns=50,
            )
            frame = pd.read_parquet(result.output_path)

        self.assertEqual(result.message_count, 2)
        self.assertEqual(list(frame["timestamp_ns"]), [100, 200])
        self.assertEqual(list(frame["timestamp_sec_from_start"]), [0.00000005, 0.00000015])
        self.assertEqual(list(frame["nested.value"]), [1.5, 1.5])

    def test_sqlite_export_writes_session_and_topic_tables(self) -> None:
        topic = "/numbers"
        reader = FakeReader([_record(topic, 100, "one"), _record(topic, 200, "two")])

        with tempfile.TemporaryDirectory() as temp_dir:
            result = export_topic_sqlite(
                reader,
                topic,
                Path(temp_dir),
                bag_start_timestamp_ns=50,
            )
            connection = sqlite3.connect(result.output_path)
            try:
                topic_count = connection.execute("select count(*) from topics").fetchone()[0]
                message_count = connection.execute("select count(*) from messages").fetchone()[0]
                export_count = connection.execute("select count(*) from exports").fetchone()[0]
                rows = connection.execute(
                    'select "timestamp_ns", "label", "nested.value" from "topic__numbers" order by "timestamp_ns"'
                ).fetchall()
                indexes = connection.execute(
                    "select name from sqlite_master where type = 'index'"
                ).fetchall()
            finally:
                connection.close()

        self.assertEqual(result.message_count, 2)
        self.assertEqual(topic_count, 1)
        self.assertEqual(message_count, 2)
        self.assertEqual(export_count, 1)
        self.assertEqual(rows, [(100, "one", 1.5), (200, "two", 1.5)])
        self.assertIn(("idx_topic__numbers_timestamp_ns",), indexes)

    def test_sqlite_topic_table_names_do_not_collapse_punctuation(self) -> None:
        reader = FakeReader([
            _record("/foo/a.b", 100, "dot"),
            _record("/foo/a-b", 200, "dash"),
        ])

        with tempfile.TemporaryDirectory() as temp_dir:
            first = export_topic_sqlite(reader, "/foo/a.b", Path(temp_dir))
            export_topic_sqlite(reader, "/foo/a-b", Path(temp_dir))
            connection = sqlite3.connect(first.output_path)
            try:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "select name from sqlite_master where type = 'table'"
                    )
                }
            finally:
                connection.close()

        self.assertIn("topic__foo__a.b", tables)
        self.assertIn("topic__foo__a-b", tables)

    def test_phase4_formats_are_implemented_and_dispatchable(self) -> None:
        topic = "/numbers"
        reader = FakeReader([_record(topic, 100, "one")])

        self.assertIn("parquet", IMPLEMENTED_EXPORTS)
        self.assertIn("sqlite", IMPLEMENTED_EXPORTS)
        with tempfile.TemporaryDirectory() as temp_dir:
            parquet = run_export(
                reader,
                topic=topic,
                fmt="parquet",
                out=Path(temp_dir),
                bag_start_timestamp_ns=0,
            )
            sqlite = run_export(
                reader,
                topic=topic,
                fmt="sqlite",
                out=Path(temp_dir),
                bag_start_timestamp_ns=0,
            )

        self.assertTrue(parquet.output_path.endswith(".parquet"))
        self.assertTrue(sqlite.output_path.endswith("session.sqlite"))


def _record(topic: str, timestamp_ns: int, label: str) -> MessageRecord:
    return MessageRecord(
        topic=topic,
        timestamp_ns=timestamp_ns,
        msgtype="example/msg/Fake",
        raw=b"raw",
        decoded=FakeMessage(label=label, nested=Nested(1.5), count=7),
    )


if __name__ == "__main__":
    unittest.main()
