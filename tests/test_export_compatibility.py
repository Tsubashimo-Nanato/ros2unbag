from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ros2unbag.core.models import MessageRecord, TopicInfo
from ros2unbag.core.session import Session, compatible_export_formats


class FakeReader:
    path = "fake"
    warnings: list[str] = []

    def __init__(self, topic: TopicInfo, records: list[MessageRecord] | None = None) -> None:
        self.topic = topic
        self.records = records or []
        self.iterated = False

    def get_topics(self) -> list[TopicInfo]:
        return [self.topic]

    def get_message_count(self, topic: str) -> int:
        return self.topic.message_count if topic == self.topic.name else 0

    def get_time_bounds(self) -> tuple[int | None, int | None]:
        return 0, 1

    def iter_messages(self, topics: list[str] | None = None) -> object:
        self.iterated = True
        topic_filter = set(topics or [])
        for record in self.records:
            if not topic_filter or record.topic in topic_filter:
                yield record

    def close(self) -> None:
        return None


class ExportCompatibilityTests(unittest.TestCase):
    def test_point_cloud_rejects_video_before_iterating_messages(self) -> None:
        topic = TopicInfo(
            name="/points",
            msgtype="sensor_msgs/msg/PointCloud2",
            message_count=1,
            category="point_cloud",
        )
        reader = FakeReader(topic)
        session = _session_for(reader)

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "not compatible"):
                session.export_topic("/points", "mp4", temp_dir)

        self.assertFalse(reader.iterated)

    def test_image_topic_keeps_flexible_data_exports(self) -> None:
        topic = TopicInfo(
            name="/camera/image_raw",
            msgtype="sensor_msgs/msg/Image",
            message_count=1,
            category="image",
        )

        self.assertIn("csv", compatible_export_formats(topic))
        self.assertIn("raw", compatible_export_formats(topic))
        self.assertIn("mp4", compatible_export_formats(topic))

    def test_unknown_topic_only_rejects_media_exports(self) -> None:
        topic = TopicInfo(
            name="/custom",
            msgtype="custom/msg/Data",
            message_count=1,
            category="custom_struct",
        )

        self.assertIn("csv", compatible_export_formats(topic))
        self.assertIn("raw", compatible_export_formats(topic))
        self.assertNotIn("png", compatible_export_formats(topic))


def _session_for(reader: FakeReader) -> Session:
    session = Session()
    session.reader = reader  # type: ignore[assignment]
    session.bag_path = Path("fake")
    session.topics = reader.get_topics()
    return session


if __name__ == "__main__":
    unittest.main()
