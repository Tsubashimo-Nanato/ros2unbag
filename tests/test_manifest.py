from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ros2unbag.core.manifest import build_manifest, sanitize_topic_name, write_manifest
from ros2unbag.core.models import Manifest, MessageRecord, TopicInfo


class FakeReader:
    path = Path("fake_bag")
    warnings: list[str] = []

    def get_topics(self) -> list[TopicInfo]:
        return [TopicInfo(name="/x", msgtype="std_msgs/msg/Float64", message_count=2)]

    def iter_messages(self, topics: list[str] | None = None) -> object:
        yield MessageRecord(
            topic="/x",
            timestamp_ns=100,
            msgtype="std_msgs/msg/Float64",
            raw=b"raw",
            decoded={"data": 1.0},
        )
        yield MessageRecord(
            topic="/x",
            timestamp_ns=200,
            msgtype="std_msgs/msg/Float64",
            raw=b"raw",
            decoded={"data": 2.0},
        )


class ManifestTests(unittest.TestCase):
    def test_sanitize_topic_name(self) -> None:
        self.assertEqual(
            sanitize_topic_name("/camera/left/image raw"),
            "camera__left__image_raw",
        )
        self.assertEqual(sanitize_topic_name("/123/topic"), "topic_123__topic")
        self.assertEqual(sanitize_topic_name("/"), "topic")

    def test_write_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "manifest.json"
            manifest = Manifest(
                source_bag_path="bag",
                created_at="2026-04-25T00:00:00+00:00",
                bag_start_timestamp_ns=1,
                bag_end_timestamp_ns=2,
                topics=[TopicInfo(name="/x", msgtype="std_msgs/msg/Float64")],
            )
            write_manifest(manifest, path)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["source_bag_path"], "bag")
            self.assertEqual(data["topics"][0]["name"], "/x")

    def test_build_manifest_reports_progress_per_message(self) -> None:
        progress_updates: list[int] = []

        manifest = build_manifest(FakeReader(), progress_callback=progress_updates.append)

        self.assertEqual(manifest.topics[0].message_count, 2)
        self.assertEqual(progress_updates, [1, 1])


if __name__ == "__main__":
    unittest.main()
