from __future__ import annotations

import unittest

from ros2_unbag.core.models import TopicInfo
from ros2_unbag.core.topic_tree import (
    build_topic_tree,
    split_topic_name,
    topic_leaf_name,
    topic_parent_path,
)


class TopicTreeTests(unittest.TestCase):
    def test_split_topic_name(self) -> None:
        self.assertEqual(split_topic_name("/camera/left/image_raw"), ["camera", "left", "image_raw"])
        self.assertEqual(split_topic_name("/"), [])

    def test_topic_leaf_and_parent_path(self) -> None:
        self.assertEqual(topic_leaf_name("/aiformula_control/game_pad/cmd_vel"), "cmd_vel")
        self.assertEqual(
            topic_parent_path("/aiformula_control/game_pad/cmd_vel"),
            "/aiformula_control/game_pad",
        )
        self.assertEqual(topic_leaf_name("/tf"), "tf")
        self.assertEqual(topic_parent_path("/tf"), "/")

    def test_build_topic_tree_counts_descendants(self) -> None:
        root = build_topic_tree(
            [
                TopicInfo(name="/camera/left/image_raw", msgtype="sensor_msgs/msg/Image"),
                TopicInfo(name="/camera/right/image_raw", msgtype="sensor_msgs/msg/Image"),
                TopicInfo(name="/tf", msgtype="tf2_msgs/msg/TFMessage"),
            ]
        )

        self.assertEqual(root.topic_count, 3)
        self.assertEqual(root.children["camera"].topic_count, 2)
        self.assertEqual(
            root.children["camera"].children["left"].children["image_raw"].topic.name,
            "/camera/left/image_raw",
        )


if __name__ == "__main__":
    unittest.main()
