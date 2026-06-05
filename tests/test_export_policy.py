from __future__ import annotations

import unittest

from ros2unbag.core.export_policy import (
    compatible_export_formats,
    default_export_formats,
    validate_export_format,
    validate_topic_export_format,
)
from ros2unbag.core.models import TopicInfo


class ExportPolicyTests(unittest.TestCase):
    def test_validate_export_format_is_case_insensitive(self) -> None:
        self.assertEqual(validate_export_format("CSV"), "csv")

    def test_image_topic_allows_media_and_data_exports(self) -> None:
        topic = TopicInfo(
            name="/camera/image_raw",
            msgtype="sensor_msgs/msg/Image",
            category="image",
        )

        self.assertEqual(
            compatible_export_formats(topic),
            ["csv", "jsonl", "npz", "parquet", "raw", "sqlite", "jpg", "mp4", "png"],
        )

    def test_point_cloud_defaults_to_native_then_data_exports_when_decoded(self) -> None:
        topic = TopicInfo(
            name="/points",
            msgtype="sensor_msgs/msg/PointCloud2",
            category="point_cloud",
            sample_summary={"decoded_available": True},
        )

        self.assertEqual(
            default_export_formats(topic),
            ["pcd", "ply", "npz", "csv", "parquet", "sqlite", "jsonl"],
        )

    def test_incompatible_topic_format_error_lists_allowed_formats(self) -> None:
        topic = TopicInfo(
            name="/points",
            msgtype="sensor_msgs/msg/PointCloud2",
            category="point_cloud",
        )

        with self.assertRaisesRegex(ValueError, "Allowed formats"):
            validate_topic_export_format(topic, "mp4")


if __name__ == "__main__":
    unittest.main()
