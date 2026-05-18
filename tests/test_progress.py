from __future__ import annotations

import unittest

from ros2unbag.cli.progress import (
    BlockBarColumn,
    _middle_truncate,
    _plain_progress_line,
    _update_batch_size,
)


class ProgressTests(unittest.TestCase):
    def test_block_bar_uses_block_characters(self) -> None:
        task = _Task(completed=5, total=10)

        rendered = BlockBarColumn(width=10).render(task).plain

        self.assertEqual(rendered, "\u2588" * 5 + "\u2591" * 5)

    def test_progress_updates_are_batched_for_large_totals(self) -> None:
        self.assertEqual(_update_batch_size(1_000), 1)
        self.assertEqual(_update_batch_size(50_000), 50)
        self.assertEqual(_update_batch_size(None), 1_000)

    def test_plain_progress_line_fits_terminal_width(self) -> None:
        line = _plain_progress_line(
            "Exporting /aiformula_perception/road_detector/mask_image as png",
            298,
            1809,
            elapsed_sec=4.0,
            width=80,
        )

        self.assertLessEqual(len(line), 80)
        self.assertIn("298/1809", line)

    def test_plain_progress_line_handles_narrow_terminal_width(self) -> None:
        line = _plain_progress_line(
            "Exporting /aiformula_perception/road_detector/mask_image as png",
            298,
            1809,
            elapsed_sec=4.0,
            width=30,
        )

        self.assertLessEqual(len(line), 30)

    def test_middle_truncate_keeps_line_bounded(self) -> None:
        self.assertEqual(_middle_truncate("abcdefghijklmnop", 10), "abc...mnop")
        self.assertEqual(_middle_truncate("abcdef", 4), "a...")


class _Task:
    def __init__(self, *, completed: int, total: int | None) -> None:
        self.completed = completed
        self.total = total


if __name__ == "__main__":
    unittest.main()
