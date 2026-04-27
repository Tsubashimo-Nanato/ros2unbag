from __future__ import annotations

import unittest

from ros2_unbag.core.models import MessageRecord, TopicInfo
from ros2_unbag.core.session import Session


class FakeReader:
    path = "fake"
    warnings: list[str] = []

    def __init__(self) -> None:
        self.records = [
            MessageRecord("/robot/cmd_vel", 100, "geometry_msgs/msg/Twist"),
            MessageRecord("/robot/cmd_vel", 150, "geometry_msgs/msg/Twist"),
            MessageRecord("/robot/imu", 90, "sensor_msgs/msg/Imu"),
            MessageRecord("/other/cmd_vel", 200, "geometry_msgs/msg/Twist"),
        ]

    def get_topics(self) -> list[TopicInfo]:
        return [
            TopicInfo(
                name="/robot/cmd_vel",
                msgtype="geometry_msgs/msg/Twist",
                message_count=2,
                first_timestamp_ns=100,
                last_timestamp_ns=150,
                duration_sec=0.00000005,
            ),
            TopicInfo(name="/robot/imu", msgtype="sensor_msgs/msg/Imu", message_count=1),
            TopicInfo(name="/other/cmd_vel", msgtype="geometry_msgs/msg/Twist", message_count=1),
        ]

    def iter_messages(self, topics: list[str] | None = None) -> object:
        topic_filter = set(topics or [])
        for record in self.records:
            if not topic_filter or record.topic in topic_filter:
                yield record

    def close(self) -> None:
        return None


class DurationTests(unittest.TestCase):
    def test_topic_duration_for_exact_topic(self) -> None:
        session = _fake_session()
        duration = session.topic_duration("/robot/cmd_vel")

        self.assertEqual(duration.topic, "/robot/cmd_vel")
        self.assertEqual(duration.message_count, 2)
        self.assertEqual(duration.first_timestamp_ns, 100)
        self.assertEqual(duration.last_timestamp_ns, 150)
        self.assertEqual(duration.bag_start_timestamp_ns, 90)
        self.assertEqual(duration.bag_end_timestamp_ns, 200)
        self.assertAlmostEqual(duration.topic_duration_sec, 0.00000005)
        self.assertAlmostEqual(duration.start_offset_sec, 0.00000001)
        self.assertAlmostEqual(duration.end_gap_sec, 0.00000005)

    def test_topic_duration_resolves_unique_leaf(self) -> None:
        session = _fake_session()
        duration = session.topic_duration("imu")

        self.assertEqual(duration.topic, "/robot/imu")
        self.assertEqual(duration.message_count, 1)
        self.assertEqual(duration.first_timestamp_ns, 90)

    def test_topic_duration_rejects_ambiguous_leaf(self) -> None:
        session = _fake_session()

        with self.assertRaisesRegex(ValueError, "Ambiguous topic leaf"):
            session.topic_duration("cmd_vel")


def _fake_session() -> Session:
    session = Session()
    session.reader = FakeReader()
    session.bag_path = "fake"  # type: ignore[assignment]
    session.topics = session.reader.get_topics()
    return session


if __name__ == "__main__":
    unittest.main()
