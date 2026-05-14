from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from ros2unbag.core.models import ExportSelection, MessageRecord, TopicInfo
from ros2unbag.core.session import Session


class MetadataBoundedReader:
    path = "fake"
    warnings: list[str] = []

    def __init__(self) -> None:
        self.full_scan_requested = False
        self.records = [
            MessageRecord(
                topic="/numbers",
                timestamp_ns=100,
                msgtype="example/msg/Fake",
                raw=b"raw",
                decoded={"value": 1},
            ),
            MessageRecord(
                topic="/numbers",
                timestamp_ns=200,
                msgtype="example/msg/Fake",
                raw=b"raw",
                decoded={"value": 2},
            ),
        ]

    def get_topics(self) -> list[TopicInfo]:
        return [
            TopicInfo(
                name="/numbers",
                msgtype="example/msg/Fake",
                message_count=2,
                first_timestamp_ns=100,
                last_timestamp_ns=200,
            )
        ]

    def get_time_bounds(self) -> tuple[int | None, int | None]:
        return 50, 300

    def get_message_count(self, topic: str) -> int:
        return 2 if topic == "/numbers" else 0

    def iter_messages(self, topics: list[str] | None = None) -> object:
        if topics is None:
            self.full_scan_requested = True
            raise AssertionError("single-topic export should not scan the whole bag")
        topic_filter = set(topics)
        for record in self.records:
            if record.topic in topic_filter:
                yield record

    def close(self) -> None:
        return None


class SessionPerformanceTests(unittest.TestCase):
    def test_single_topic_export_uses_metadata_bounds_without_full_bag_scan(self) -> None:
        reader = MetadataBoundedReader()
        session = Session()
        session.reader = reader  # type: ignore[assignment]
        session.bag_path = Path("fake")
        session.topics = reader.get_topics()

        with tempfile.TemporaryDirectory() as temp_dir:
            result = session.export_topic("/numbers", "csv", temp_dir)
            with Path(result.output_path).open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        self.assertFalse(reader.full_scan_requested)
        self.assertEqual(result.message_count, 2)
        self.assertEqual(rows[0]["timestamp_sec_from_start"], "5e-08")

    def test_selected_exports_reuse_metadata_bounds(self) -> None:
        reader = MetadataBoundedReader()
        session = Session()
        session.reader = reader  # type: ignore[assignment]
        session.bag_path = Path("fake")
        session.topics = reader.get_topics()

        with tempfile.TemporaryDirectory() as temp_dir:
            results = session.export_selected(
                [ExportSelection(topic="numbers", format="raw", out_dir=temp_dir)]
            )

        self.assertFalse(reader.full_scan_requested)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].message_count, 2)


if __name__ == "__main__":
    unittest.main()
