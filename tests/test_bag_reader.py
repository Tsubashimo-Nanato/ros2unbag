from __future__ import annotations

import unittest

from ros2unbag.core.bag_reader import open_bag_reader
from ros2unbag.core.session import Session


class BagReaderTests(unittest.TestCase):
    def test_open_bag_reader_rejects_unknown_backend(self) -> None:
        with self.assertRaisesRegex(ValueError, "backend must be one of"):
            open_bag_reader("missing", backend="bad-backend")

    def test_failed_session_open_does_not_leave_bag_path_set(self) -> None:
        session = Session()

        with self.assertRaises(ValueError):
            session.open_bag("missing", backend="bad-backend")

        self.assertEqual(session.backend, "auto")
        self.assertIsNone(session.bag_path)
        self.assertIsNone(session.reader)


if __name__ == "__main__":
    unittest.main()
