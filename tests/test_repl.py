from __future__ import annotations

import unittest

from prompt_toolkit.document import Document

from ros2_unbag.cli.repl import Ros2UnbagCompleter, split_repl_line
from ros2_unbag.core.models import TopicInfo
from ros2_unbag.core.session import Session


class ReplTests(unittest.TestCase):
    def test_split_repl_line_preserves_windows_paths(self) -> None:
        tokens = split_repl_line(r"open .\bag\demo --backend sqlite")
        self.assertEqual(tokens, ["open", r".\bag\demo", "--backend", "sqlite"])

    def test_completes_format_values(self) -> None:
        completer = Ros2UnbagCompleter(Session())
        completions = list(
            completer.get_completions(Document("export /topic --format "), object())
        )
        values = {item.text for item in completions}
        self.assertIn("csv", values)
        self.assertIn("raw", values)

    def test_completes_open_topics(self) -> None:
        session = Session()
        session.topics = [
            TopicInfo(name="/camera/image_raw", msgtype="sensor_msgs/msg/Image"),
            TopicInfo(name="/imu", msgtype="sensor_msgs/msg/Imu"),
        ]
        completer = Ros2UnbagCompleter(session)
        completions = list(completer.get_completions(Document("export /c"), object()))
        self.assertEqual([item.text for item in completions], ["/camera/image_raw"])

    def test_completes_topics_for_duration_command(self) -> None:
        session = Session()
        session.topics = [
            TopicInfo(name="/camera/image_raw", msgtype="sensor_msgs/msg/Image"),
            TopicInfo(name="/imu", msgtype="sensor_msgs/msg/Imu"),
        ]
        completer = Ros2UnbagCompleter(session)
        completions = list(completer.get_completions(Document("dur /i"), object()))
        self.assertEqual([item.text for item in completions], ["/imu"])


if __name__ == "__main__":
    unittest.main()
