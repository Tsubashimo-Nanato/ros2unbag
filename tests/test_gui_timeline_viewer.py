from __future__ import annotations

import importlib.util
import os
import unittest

from ros2unbag.core.models import TopicInfo
from ros2unbag.gui.timeline_viewer import TimelineViewer


if importlib.util.find_spec("PySide6") is None:
    raise unittest.SkipTest("PySide6 is not installed")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6 import QtWidgets  # noqa: E402


class DummyReader:
    def close(self) -> None:
        return None


class GuiTimelineViewerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_window_menu_exposes_dock_toggles(self) -> None:
        viewer = TimelineViewer()
        try:
            self.assertEqual(
                [action.text() for action in viewer.window.menuBar().actions()],
                ["File", "Windows"],
            )
            self.assertIn("Version...", [action.text() for action in viewer._file_menu.actions()])
            self.assertEqual(
                list(viewer._dock_widgets),
                ["Topic list", "Main view", "Properties", "Output"],
            )
            for dock in viewer._dock_widgets.values():
                self.assertTrue(dock.toggleViewAction().isCheckable())
        finally:
            viewer.window.close()

    def test_topic_tree_is_folded_after_population(self) -> None:
        viewer = TimelineViewer()
        try:
            viewer.session.reader = DummyReader()  # type: ignore[assignment]
            viewer.session.topics = [
                TopicInfo(
                    name="/aiformula/camera/image_raw",
                    msgtype="sensor_msgs/msg/Image",
                    category="image",
                )
            ]
            viewer._populate_topics()
            top = viewer.topic_tree.topLevelItem(0)
            self.assertIsNotNone(top)
            self.assertFalse(top.isExpanded())
            self.assertEqual(viewer._panes[0].title_label.text(), "View 1: Drop topic here")
        finally:
            viewer.window.close()

    def test_playback_rate_selector_updates_rate(self) -> None:
        viewer = TimelineViewer()
        try:
            viewer.rate_box.setCurrentText("4x")
            self.assertEqual(viewer._playback_rate, 4.0)
        finally:
            viewer.window.close()


if __name__ == "__main__":
    unittest.main()
