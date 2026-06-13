from __future__ import annotations

import unittest

from ros2unbag.core.export_policy import (
    IMPLEMENTED_EXPORTS,
    compatible_export_formats,
    default_export_formats,
    validate_export_format,
)
from ros2unbag.core.export_runner import EXPORT_HANDLERS, run_export
from ros2unbag.core.models import TopicInfo


class ExportPolicyTests(unittest.TestCase):
    def test_policy_and_runner_formats_stay_aligned(self) -> None:
        self.assertEqual(IMPLEMENTED_EXPORTS, set(EXPORT_HANDLERS))

    def test_validate_export_format_reports_allowed_formats(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported format 'bagel'.*csv.*sqlite"):
            validate_export_format("bagel")

    def test_default_exports_follow_decoded_topic_category(self) -> None:
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

    def test_image_formats_keep_data_exports_available(self) -> None:
        topic = TopicInfo(
            name="/camera",
            msgtype="sensor_msgs/msg/Image",
            category="image",
        )

        formats = compatible_export_formats(topic)

        self.assertIn("csv", formats)
        self.assertIn("raw", formats)
        self.assertIn("mp4", formats)

    def test_runner_rejects_unregistered_implemented_format(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported implemented export format: nope"):
            run_export(
                object(),  # type: ignore[arg-type]
                topic="/topic",
                fmt="nope",
                out=object(),  # type: ignore[arg-type]
                bag_start_timestamp_ns=None,
            )


if __name__ == "__main__":
    unittest.main()
