from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from ros2unbag.core.lane_lines import LaneFrame, LaneOverlayData, LanePoint, LaneSeries
from ros2unbag.core.models import MessageRecord
from ros2unbag.core.models import TopicInfo
from ros2unbag.gui.timeline_viewer import MAX_RENDERED_PLAYBACK_FRAMES, TimelineViewer


if importlib.util.find_spec("PySide6") is None:
    raise unittest.SkipTest("PySide6 is not installed")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402


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
                ["File", "Theme", "Windows"],
            )
            self.assertIn("Version...", [action.text() for action in viewer._file_menu.actions()])
            self.assertEqual(
                [action.text() for action in viewer._theme_menu.actions()],
                ["Bright mode", "Dark mode"],
            )
            self.assertEqual(
                list(viewer._dock_widgets),
                ["Topic list", "Main view", "Lane line overlay", "Properties", "Output"],
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

    def test_topic_panel_exposes_search_and_fold_controls(self) -> None:
        viewer = TimelineViewer()
        try:
            self.assertEqual(viewer.topic_search.placeholderText(), "Search topics")
            self.assertEqual(viewer.topic_expand_button.text(), "Expand")
            self.assertEqual(viewer.topic_collapse_button.text(), "Collapse")
            self.assertIs(viewer.topic_dock.widget(), viewer.topic_panel)
        finally:
            viewer.window.close()

    def test_topic_tree_distinguishes_groups_from_topic_leaves(self) -> None:
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

            root = viewer.topic_tree.topLevelItem(0)
            camera = root.child(0)
            leaf = camera.child(0)

            self.assertTrue(root.font(0).bold())
            self.assertFalse(root.flags() & QtCore.Qt.ItemFlag.ItemIsSelectable)
            self.assertTrue(leaf.flags() & QtCore.Qt.ItemFlag.ItemIsSelectable)
            self.assertTrue(leaf.flags() & QtCore.Qt.ItemFlag.ItemIsDragEnabled)
            self.assertEqual(
                leaf.data(0, QtCore.Qt.ItemDataRole.UserRole),
                "/aiformula/camera/image_raw",
            )
        finally:
            viewer.window.close()

    def test_topic_search_filters_to_matching_topic_path(self) -> None:
        viewer = TimelineViewer()
        try:
            viewer.session.reader = DummyReader()  # type: ignore[assignment]
            viewer.session.topics = [
                TopicInfo(
                    name="/aiformula/camera/image_raw",
                    msgtype="sensor_msgs/msg/Image",
                    category="image",
                ),
                TopicInfo(
                    name="/aiformula/imu",
                    msgtype="sensor_msgs/msg/Imu",
                    category="unknown_raw",
                ),
                TopicInfo(
                    name="/vehicle/points",
                    msgtype="sensor_msgs/msg/PointCloud2",
                    category="point_cloud",
                ),
            ]
            viewer._populate_topics()

            viewer.topic_search.setText("camera")

            aiformula = _tree_item(viewer.topic_tree, "aiformula")
            camera = _tree_item(viewer.topic_tree, "camera")
            imu = _tree_item(viewer.topic_tree, "imu")
            vehicle = _tree_item(viewer.topic_tree, "vehicle")
            self.assertFalse(aiformula.isHidden())
            self.assertFalse(camera.isHidden())
            self.assertTrue(imu.isHidden())
            self.assertTrue(vehicle.isHidden())
            self.assertTrue(aiformula.isExpanded())
        finally:
            viewer.window.close()

    def test_topic_expand_and_collapse_buttons_control_tree(self) -> None:
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
            root = viewer.topic_tree.topLevelItem(0)

            viewer.topic_expand_button.click()
            self.assertTrue(root.isExpanded())

            viewer.topic_search.setText("camera")
            viewer.topic_collapse_button.click()
            self.assertEqual(viewer.topic_search.text(), "")
            self.assertFalse(root.isExpanded())
            self.assertFalse(root.isHidden())
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
            self.assertIn("QTreeWidget::indicator", viewer.window.styleSheet())
        finally:
            viewer.window.close()

    def test_theme_menu_switches_modes(self) -> None:
        viewer = TimelineViewer()
        try:
            viewer._theme_actions["light"].trigger()
            self.assertEqual(viewer._theme, "light")
            self.assertTrue(viewer._theme_actions["light"].isChecked())
            self.assertFalse(viewer._theme_actions["dark"].isChecked())

            viewer._theme_actions["dark"].trigger()
            self.assertEqual(viewer._theme, "dark")
            self.assertFalse(viewer._theme_actions["light"].isChecked())
            self.assertTrue(viewer._theme_actions["dark"].isChecked())
        finally:
            viewer.window.close()

    def test_default_theme_is_dark_without_saved_preference(self) -> None:
        settings = QtCore.QSettings("TsubashimoNanato", "ros2unbag")
        previous = settings.value("ui/theme", "")
        settings.remove("ui/theme")
        viewer = TimelineViewer()
        try:
            self.assertEqual(viewer._theme, "dark")
            self.assertTrue(viewer._theme_actions["dark"].isChecked())
            self.assertIn("#101010", viewer.window.styleSheet())
        finally:
            viewer.window.close()
            if previous:
                settings.setValue("ui/theme", previous)
            else:
                settings.remove("ui/theme")

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

    def test_lane_overlay_detects_topics_and_loads_frames(self) -> None:
        viewer = TimelineViewer()
        calls = []
        try:
            def fake_background(**kwargs: object) -> None:
                calls.append(kwargs)
                kwargs["on_success"](_lane_overlay_data())  # type: ignore[index, operator]

            viewer._run_background = fake_background  # type: ignore[method-assign]
            viewer.session.reader = DummyReader()  # type: ignore[assignment]
            viewer.session.bag_path = Path("fake")
            viewer._prepare_lane_overlay([
                _lane_topic("center"),
                _lane_topic("left"),
                _lane_topic("right"),
            ])

            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]["title"], "Loading lane line overlay")
            self.assertIsNotNone(viewer._lane_overlay_data)
            for role in ("center", "left", "right"):
                self.assertTrue(viewer.lane_overlay.checkboxes[role].isEnabled())
                self.assertTrue(viewer.lane_overlay.checkboxes[role].isChecked())
            self.assertIn("center: 1 frames", viewer.lane_overlay.status_label.text())
        finally:
            viewer.window.close()

    def test_lane_overlay_checkbox_toggle_changes_visible_series(self) -> None:
        viewer = TimelineViewer()
        try:
            viewer.lane_overlay.set_topics({
                "center": _lane_topic("center"),
                "left": _lane_topic("left"),
                "right": _lane_topic("right"),
            })
            viewer.lane_overlay.set_data(_lane_overlay_data())

            viewer.lane_overlay.checkboxes["right"].setChecked(False)

            self.assertEqual(viewer.lane_overlay.visible_roles(), ["center", "left"])
            self.assertEqual(viewer.lane_overlay.plot._visible_roles, {"center", "left"})
        finally:
            viewer.window.close()

    def test_lane_overlay_receives_timeline_timestamp(self) -> None:
        viewer = TimelineViewer()
        try:
            viewer._bag_start_ns = 1_000
            viewer.time_input.blockSignals(True)
            viewer.time_input.setValue(0.5)
            viewer.time_input.blockSignals(False)

            viewer._update_preview()

            self.assertEqual(viewer.lane_overlay.current_timestamp_ns, 500_001_000)
        finally:
            viewer.window.close()

    def test_lane_overlay_plot_renders_lane_pixels(self) -> None:
        viewer = TimelineViewer()
        try:
            viewer.lane_overlay.set_topics({
                "center": _lane_topic("center"),
                "left": _lane_topic("left"),
                "right": _lane_topic("right"),
            })
            viewer.lane_overlay.set_data(_lane_overlay_data())
            viewer.lane_overlay.show_at_timestamp(100)
            viewer.lane_overlay.plot.resize(360, 280)
            image = QtGui.QImage(
                viewer.lane_overlay.plot.size(),
                QtGui.QImage.Format.Format_ARGB32,
            )
            image.fill(QtGui.QColor("#000000"))
            painter = QtGui.QPainter(image)
            viewer.lane_overlay.plot.render(painter, viewer.QtCore.QPoint(0, 0))
            painter.end()

            amber_pixels = 0
            for y in range(image.height()):
                for x in range(image.width()):
                    color = image.pixelColor(x, y)
                    if color.red() > 180 and color.green() > 130 and color.blue() < 130:
                        amber_pixels += 1

            self.assertGreater(amber_pixels, 0)
        finally:
            viewer.window.close()

    def test_lane_topic_render_uses_lane_plot_without_image_warning(self) -> None:
        viewer = TimelineViewer()
        warnings: list[str] = []
        try:
            topics = {role: _lane_topic(role) for role in ("center", "left", "right")}
            viewer._bag_start_ns = 0
            viewer._lane_overlay_data = _lane_overlay_data()
            viewer.lane_overlay.set_topics(topics)
            viewer.lane_overlay.set_data(viewer._lane_overlay_data)
            viewer._show_warning = lambda message: warnings.append(message)  # type: ignore[method-assign]
            pane = viewer._panes[0]
            pane.set_topic(topics["center"].name, topics["center"])

            self.assertTrue(pane.ensure_rendered_for_playback())

            self.assertEqual(warnings, [])
            self.assertIs(pane.stack.currentWidget(), pane.lane_plot)
            self.assertEqual(pane.lane_plot._visible_roles, {"center", "left", "right"})
        finally:
            viewer.window.close()

    def test_lane_view_uses_checked_topic_tree_roles(self) -> None:
        viewer = TimelineViewer()
        try:
            topics = [_lane_topic(role) for role in ("center", "left", "right")]
            viewer.session.reader = DummyReader()  # type: ignore[assignment]
            viewer.session.topics = topics
            viewer._bag_start_ns = 0
            viewer._lane_overlay_data = _lane_overlay_data()
            viewer._populate_topics()
            _tree_item(viewer.topic_tree, "center").setCheckState(
                0,
                QtCore.Qt.CheckState.Checked,
            )
            _tree_item(viewer.topic_tree, "right").setCheckState(
                0,
                QtCore.Qt.CheckState.Checked,
            )
            pane = viewer._panes[0]
            pane.set_topic(topics[0].name, topics[0])
            pane.show_at_timestamp(100)

            self.assertIs(pane.stack.currentWidget(), pane.lane_plot)
            self.assertEqual(pane.lane_plot._visible_roles, {"center", "right"})
        finally:
            viewer.window.close()

    def test_lane_overlay_missing_topics_stays_empty(self) -> None:
        viewer = TimelineViewer()
        calls = []
        try:
            viewer._run_background = lambda **kwargs: calls.append(kwargs)  # type: ignore[method-assign]
            viewer._prepare_lane_overlay([
                TopicInfo(
                    name="/camera",
                    msgtype="sensor_msgs/msg/Image",
                    category="image",
                )
            ])

            self.assertEqual(calls, [])
            self.assertEqual(viewer.lane_overlay.visible_roles(), [])
            self.assertIn("No lane line topics", viewer.lane_overlay.status_label.text())
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

def _lane_topic(role: str) -> TopicInfo:
    return TopicInfo(
        name=f"/aiformula_perception/lane_line_publisher/lane_lines/{role}",
        msgtype="sensor_msgs/msg/PointCloud2",
        category="point_cloud",
        message_count=1,
    )


def _lane_overlay_data() -> LaneOverlayData:
    return LaneOverlayData(
        series_by_role={
            role: LaneSeries(
                role=role,
                topic=_lane_topic(role).name,
                frames=[
                    LaneFrame(
                        timestamp_ns=100,
                        points=(LanePoint(1.0, 2.0), LanePoint(3.0, 4.0)),
                    )
                ],
            )
            for role in ("center", "left", "right")
        }
    )


def _tree_item(tree: QtWidgets.QTreeWidget, text: str) -> QtWidgets.QTreeWidgetItem:
    for index in range(tree.topLevelItemCount()):
        found = _tree_item_from(tree.topLevelItem(index), text)
        if found is not None:
            return found
    raise AssertionError(f"Tree item not found: {text}")


def _tree_item_from(
    item: QtWidgets.QTreeWidgetItem,
    text: str,
) -> QtWidgets.QTreeWidgetItem | None:
    if item.text(0) == text:
        return item
    for index in range(item.childCount()):
        found = _tree_item_from(item.child(index), text)
        if found is not None:
            return found
    return None


if __name__ == "__main__":
    unittest.main()
