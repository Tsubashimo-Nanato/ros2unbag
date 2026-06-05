from __future__ import annotations

import importlib.util
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from ros2unbag.core.models import MessageRecord
from ros2unbag.core.models import TopicInfo
from ros2unbag.gui.timeline_viewer import MAX_RENDERED_PLAYBACK_FRAMES, TimelineViewer


if importlib.util.find_spec("PySide6") is None:
    raise unittest.SkipTest("PySide6 is not installed")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6 import QtWidgets  # noqa: E402


class DummyReader:
    def close(self) -> None:
        return None


class ImageReader:
    def __init__(self, count: int) -> None:
        self.count = count

    def iter_messages(self, topics: list[str] | None = None) -> object:
        topic = (topics or ["/camera"])[0]
        for index in range(self.count):
            yield MessageRecord(
                topic=topic,
                timestamp_ns=index,
                msgtype="sensor_msgs/msg/Image",
                raw=b"raw",
                decoded=object(),
            )

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
            self.assertGreaterEqual(viewer.topic_tree.columnWidth(0), 150)
        finally:
            viewer.window.close()

    def test_central_spacer_is_collapsed_for_dock_layout(self) -> None:
        viewer = TimelineViewer()
        try:
            self.assertEqual(viewer.central_spacer.maximumWidth(), 0)
            self.assertEqual(viewer.central_spacer.minimumWidth(), 0)
        finally:
            viewer.window.close()

    def test_show_without_open_bag_does_not_crash_autosize(self) -> None:
        viewer = TimelineViewer()
        try:
            viewer._update_settings.setValue("updates/mode", "off")
            viewer.show()
            for _index in range(10):
                self.app.processEvents()
            self.assertIsNone(viewer.session.reader)
        finally:
            viewer.window.close()

    def test_topic_tree_width_uses_topic_data(self) -> None:
        viewer = TimelineViewer()
        try:
            viewer.session.reader = DummyReader()  # type: ignore[assignment]
            viewer.session.topics = [
                TopicInfo(
                    name="/aiformula_perception/road_detector/annotated_mask_image",
                    msgtype="sensor_msgs/msg/Image",
                    category="mask_candidate",
                    message_count=1809,
                ),
                TopicInfo(
                    name="/aiformula_visualization/processed_point_cloud",
                    msgtype="sensor_msgs/msg/PointCloud2",
                    category="point_cloud",
                    message_count=1821,
                ),
            ]
            viewer._populate_topics()
            self.assertGreaterEqual(viewer._preferred_topic_width(), 360)
            self.assertGreaterEqual(viewer.topic_tree.minimumWidth(), 360)
        finally:
            viewer.window.close()

    def test_playback_rate_selector_updates_rate(self) -> None:
        viewer = TimelineViewer()
        try:
            viewer.rate_box.setCurrentText("4x")
            self.assertEqual(viewer._playback_rate, 4.0)
        finally:
            viewer.window.close()

    def test_theme_switch_updates_stylesheet(self) -> None:
        viewer = TimelineViewer()
        try:
            viewer._set_theme("dark")
            self.assertEqual(viewer._theme, "dark")
            self.assertIn("#101010", viewer.window.styleSheet())
            self.assertIn("QHeaderView::section", self.app.styleSheet())
            self.assertIn("QWidget#propertiesPanel", self.app.styleSheet())

            viewer._set_theme("light")
            self.assertEqual(viewer._theme, "light")
            self.assertIn("#edf0f3", viewer.window.styleSheet())
        finally:
            viewer.window.close()

    def test_update_check_starts_background_job(self) -> None:
        viewer = TimelineViewer()
        calls = []
        try:
            def fake_background(**kwargs: object) -> None:
                calls.append(kwargs)

            viewer._run_background = fake_background  # type: ignore[method-assign]
            viewer._start_update_check(show_no_update=False)

            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]["title"], "Checking for updates")
        finally:
            viewer.window.close()

    def test_image_render_cache_is_bounded(self) -> None:
        viewer = TimelineViewer()
        try:
            topic = "/camera"
            topic_info = TopicInfo(
                name=topic,
                msgtype="sensor_msgs/msg/Image",
                category="image",
                message_count=MAX_RENDERED_PLAYBACK_FRAMES + 25,
            )
            viewer.session.reader = ImageReader(MAX_RENDERED_PLAYBACK_FRAMES + 25)  # type: ignore[assignment]
            viewer.session.topics = [topic_info]
            viewer._bag_start_ns = 0
            pane = viewer._panes[0]
            pane.set_topic(topic, topic_info)
            frame = SimpleNamespace(
                array=np.zeros((4, 4, 3), dtype=np.uint8),
                width=4,
                height=4,
                encoding="bgr8",
                warnings=[],
            )

            with patch("ros2unbag.gui.timeline_viewer._decode_record_frame", return_value=frame):
                self.assertTrue(pane.ensure_rendered_for_playback())

            self.assertEqual(len(pane.rendered_frames), MAX_RENDERED_PLAYBACK_FRAMES)
        finally:
            viewer.window.close()


if __name__ == "__main__":
    unittest.main()
