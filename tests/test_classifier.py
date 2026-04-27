from __future__ import annotations

import dataclasses
import unittest

from ros2_unbag.core.models import MessageRecord, TopicInfo
from ros2_unbag.core.type_classifier import classify_topic


@dataclasses.dataclass
class FakeVector:
    x: float
    y: float
    z: float


class ClassifierTests(unittest.TestCase):
    def test_known_scalar_type(self) -> None:
        topic = TopicInfo(name="/speed", msgtype="std_msgs/msg/Float64")
        self.assertEqual(classify_topic(topic, []), "scalar")

    def test_known_image_type(self) -> None:
        topic = TopicInfo(name="/camera/image_raw", msgtype="sensor_msgs/msg/Image")
        self.assertEqual(classify_topic(topic, []), "image")

    def test_binary_image_with_mask_hint_is_mask_candidate(self) -> None:
        topic = TopicInfo(
            name="/perception/mask_image",
            msgtype="sensor_msgs/msg/Image",
            sample_summary={
                "mask_detection": {
                    "unique_values_mostly_binary": True,
                    "confidence": 0.66,
                }
            },
        )
        record = MessageRecord(
            topic=topic.name,
            timestamp_ns=10,
            msgtype=topic.msgtype,
            decoded=object(),
        )

        self.assertEqual(classify_topic(topic, [record]), "mask_candidate")

    def test_flat_numeric_unknown_decoded_type(self) -> None:
        topic = TopicInfo(name="/custom/vector", msgtype="custom/msg/Vector")
        record = MessageRecord(
            topic=topic.name,
            timestamp_ns=10,
            msgtype=topic.msgtype,
            decoded=FakeVector(1.0, 2.0, 3.0),
        )
        self.assertEqual(classify_topic(topic, [record]), "vector_struct")

    def test_unknown_raw_when_no_decoded_samples(self) -> None:
        topic = TopicInfo(name="/custom/raw", msgtype="custom/msg/Raw")
        self.assertEqual(classify_topic(topic, []), "unknown_raw")


if __name__ == "__main__":
    unittest.main()
