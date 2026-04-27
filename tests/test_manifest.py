from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ros2_unbag.core.manifest import sanitize_topic_name, write_manifest
from ros2_unbag.core.models import Manifest, TopicInfo


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


if __name__ == "__main__":
    unittest.main()
