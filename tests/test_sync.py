from __future__ import annotations

import unittest

from ros2_unbag.core.models import MessageRecord
from ros2_unbag.core.topic_indexer import TimestampIndex


class TimestampIndexTests(unittest.TestCase):
    def test_find_nearest_middle(self) -> None:
        index = TimestampIndex()
        for timestamp in [100, 200, 400]:
            index.add(MessageRecord("/a", timestamp, "std_msgs/msg/Float64"))
        index.finalize()

        nearest = index.find_nearest("/a", 260)
        self.assertEqual(nearest.nearest_timestamp_ns, 200)
        self.assertEqual(nearest.before_timestamp_ns, 200)
        self.assertEqual(nearest.after_timestamp_ns, 400)
        self.assertEqual(nearest.delta_ns, -60)

    def test_find_nearest_empty_topic(self) -> None:
        index = TimestampIndex()
        nearest = index.find_nearest("/missing", 10)
        self.assertIsNone(nearest.nearest_timestamp_ns)
        self.assertIsNone(nearest.delta_ns)


if __name__ == "__main__":
    unittest.main()
