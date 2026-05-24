from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from ros2unbag.core.decoder import decode_compressed_image, decode_sensor_image
from ros2unbag.core.models import ExportSelection, TopicInfo
from ros2unbag.core.preview import (
    PreviewService,
    PreviewSessionSettings,
    TopicDisplaySettings,
    save_preview_settings,
)
from ros2unbag.core.session import Session, compatible_export_formats
from ros2unbag.core.update_check import UpdateInfo, check_for_update, current_version
from ros2unbag.cli.upgrade import build_upgrade_plan, run_upgrade
from ros2unbag.gui.renderers import create_point_cloud_renderer


TOPIC_MIME = "application/x-ros2unbag-topic"
IMAGE_CATEGORIES = {"image", "compressed_image", "mask_candidate"}


@dataclass(slots=True)
class RenderedFrame:
    timestamp_ns: int
    pixmap: Any
    width: int
    height: int
    encoding: str


class TimelineViewer:
    """Offline bag viewer shell for Windows-first ros2unbag workflows."""

    def __init__(self, bag_path: str | Path | None = None) -> None:
        self.QtCore, self.QtGui, self.QtWidgets = _require_pyside6()
        self.TopicTreeWidget = _create_topic_tree_class(self.QtWidgets, self.QtCore)
        self.TopicViewPane = _create_view_pane_class(
            self.QtWidgets, self.QtCore, self.QtGui
        )
        self.session = Session()
        self.preview: PreviewService | None = None
        self.settings = PreviewSessionSettings()
        self._topic_by_item: dict[int, str] = {}
        self._topic_info_by_name: dict[str, TopicInfo] = {}
        self._bag_start_ns: int | None = None
        self._bag_end_ns: int | None = None
        self._playback_fps = 30.0
        self._grid_rows = 1
        self._grid_cols = 1
        self._panes: list[Any] = []
        self._popout_panes: list[Any] = []
        self._active_pane: Any | None = None
        self._maximized_pane: Any | None = None
        self._dock_widgets: dict[str, Any] = {}
        self._windows_menu: Any | None = None
        self._next_view_id = 1
        self._playback_rate = 1.0
        self._update_settings = self.QtCore.QSettings("TsubashimoNanato", "ros2unbag")
        self._latest_update_info: UpdateInfo | None = None

        self.window = _create_drop_window(self.QtWidgets, self.QtCore, self.open_bag)
        self.window.setWindowTitle("ros2unbag Timeline Viewer")
        self.window.resize(1280, 760)
        self._build_ui()
        if bag_path is not None:
            self.open_bag(bag_path)
        self.QtCore.QTimer.singleShot(500, self._maybe_offer_startup_update_check)

    def show(self) -> None:
        self.window.show()

    def open_bag(self, bag_path: str | Path) -> None:
        path = Path(bag_path)
        self._log(f"Opening {path}")
        self._start_progress(f"Opening {path.name}", None)
        try:
            topics = self.session.open_bag(path)
            self.preview = PreviewService(self.session)
            self._topic_info_by_name = {topic.name: topic for topic in topics}
            self.settings.bag_path = str(path)
            self.settings.topics = {
                topic.name: TopicDisplaySettings(topic=topic.name)
                for topic in topics
            }
            for pane in self._all_panes():
                pane.clear_topic()
            self._populate_topics()
            self._load_metadata_time_bounds()
            self._autosize_topic_columns()
            self._autosize_docks()
            self._log(f"Opened {path} ({len(topics)} topics)")
        except Exception as exc:
            self._show_warning(f"Failed to open bag: {exc}")
        finally:
            self._finish_progress()

    def assign_topic_to_pane(self, pane: Any, topic: str) -> None:
        topic_info = self._topic_info_by_name.get(topic)
        if topic_info is None:
            self._log(f"Topic not found: {topic}")
            return
        pane.set_topic(topic, topic_info)
        self._active_pane = pane
        self._apply_topic_settings(topic)
        self._request_preview_update()

    def split_pane(self, pane: Any, direction: str) -> None:
        if len(self._panes) >= 16:
            self._show_warning("The viewer grid is limited to 4x4 panes.")
            return
        if direction == "horizontal" and self._grid_cols < 4:
            self._grid_cols += 1
        elif direction == "vertical" and self._grid_rows < 4:
            self._grid_rows += 1
        elif self._grid_rows < 4:
            self._grid_rows += 1
        elif self._grid_cols < 4:
            self._grid_cols += 1
        else:
            self._show_warning("The viewer grid is limited to 4x4 panes.")
            return

        new_pane = self._new_pane()
        insert_at = self._panes.index(pane) + 1 if pane in self._panes else len(self._panes)
        self._panes.insert(insert_at, new_pane)
        self._layout_panes()

    def toggle_maximize_pane(self, pane: Any) -> None:
        if self._maximized_pane is pane:
            self._maximized_pane = None
            for item in self._panes:
                item.setVisible(True)
            return
        self._maximized_pane = pane
        for item in self._panes:
            item.setVisible(item is pane)

    def delete_pane(self, pane: Any) -> None:
        if pane in self._popout_panes:
            self._popout_panes.remove(pane)
            pane.window().close()
            return
        if len(self._panes) <= 1:
            pane.clear_topic()
            return
        if pane in self._panes:
            self._panes.remove(pane)
            pane.setParent(None)
            if self._active_pane is pane:
                self._active_pane = self._panes[0]
            if self._maximized_pane is pane:
                self._maximized_pane = None
            self._layout_panes()

    def popout_pane(self, pane: Any) -> None:
        dialog = self.QtWidgets.QDialog(self.window)
        dialog.setWindowTitle(pane.topic or "ros2unbag view")
        dialog.resize(760, 520)
        layout = self.QtWidgets.QVBoxLayout(dialog)
        popout = self._new_pane(parent=dialog)
        if pane.topic is not None and pane.topic_info is not None:
            popout.set_topic(pane.topic, pane.topic_info)
            popout.show_at_timestamp(self._current_timestamp_ns())
        layout.addWidget(popout)
        self._popout_panes.append(popout)

        def cleanup(_result: int = 0) -> None:
            if popout in self._popout_panes:
                self._popout_panes.remove(popout)

        dialog.finished.connect(cleanup)
        dialog.show()

    def _build_ui(self) -> None:
        QtWidgets = self.QtWidgets
        QtCore = self.QtCore

        self._build_menus()
        self.window.setDockOptions(
            QtWidgets.QMainWindow.DockOption.AllowNestedDocks
            | QtWidgets.QMainWindow.DockOption.AllowTabbedDocks
            | QtWidgets.QMainWindow.DockOption.AnimatedDocks
        )
        self.window.setStyleSheet(
            """
            QDockWidget::title {
                padding: 4px 6px;
                font-weight: 600;
            }
            QGroupBox {
                font-weight: 600;
                margin-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }
            QFrame#topicViewPane {
                border: 1px solid #9a9a9a;
                border-radius: 4px;
                background: #f8f8f8;
            }
            QToolButton {
                padding: 2px 6px;
            }
            """
        )

        placeholder = QtWidgets.QLabel("Use File > Import bag... or drop a bag folder here.")
        placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        placeholder.setStyleSheet("color: #666; font-size: 14px;")
        self.window.setCentralWidget(placeholder)

        self.topic_tree = self.TopicTreeWidget()
        self.topic_tree.setHeaderLabels(["Topic", "Category", "Count"])
        self.topic_tree.setDragEnabled(True)
        self.topic_tree.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.DragOnly)
        self.topic_tree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.topic_tree.itemSelectionChanged.connect(self._on_topic_selection_changed)
        self.topic_tree.itemDoubleClicked.connect(self._on_topic_double_clicked)
        self.topic_tree.setMinimumWidth(260)

        self.view_grid_widget = QtWidgets.QWidget()
        self.view_grid = QtWidgets.QGridLayout(self.view_grid_widget)
        self.view_grid.setContentsMargins(6, 6, 6, 6)
        self.view_grid.setSpacing(6)
        first_pane = self._new_pane()
        self._panes.append(first_pane)
        self._active_pane = first_pane
        self._layout_panes()

        settings_panel = QtWidgets.QWidget()
        settings_layout = QtWidgets.QFormLayout(settings_panel)
        settings_layout.setContentsMargins(10, 10, 10, 10)
        settings_layout.setSpacing(8)
        self.visible_check = QtWidgets.QCheckBox()
        self.visible_check.setChecked(True)
        self.color_button = QtWidgets.QPushButton("Color")
        self.point_size = QtWidgets.QDoubleSpinBox()
        self.point_size.setRange(0.1, 20.0)
        self.point_size.setValue(2.0)
        self.decimation = QtWidgets.QSpinBox()
        self.decimation.setRange(1, 1_000)
        self.decimation.setValue(4)
        self.opacity = QtWidgets.QDoubleSpinBox()
        self.opacity.setRange(0.0, 1.0)
        self.opacity.setSingleStep(0.1)
        self.opacity.setValue(1.0)
        self.sync_offset = QtWidgets.QDoubleSpinBox()
        self.sync_offset.setRange(-3600.0, 3600.0)
        self.sync_offset.setDecimals(3)
        self.save_settings_button = QtWidgets.QPushButton("Save sidecar")
        self.save_settings_button.clicked.connect(self._save_sidecar)
        settings_layout.addRow("Visible", self.visible_check)
        settings_layout.addRow("Color", self.color_button)
        settings_layout.addRow("Point size", self.point_size)
        settings_layout.addRow("Decimation", self.decimation)
        settings_layout.addRow("Opacity", self.opacity)
        settings_layout.addRow("Sync offset s", self.sync_offset)
        settings_layout.addRow(self.save_settings_button)

        settings_scroll = QtWidgets.QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setWidget(settings_panel)

        main_panel = QtWidgets.QWidget()
        main_layout = QtWidgets.QVBoxLayout(main_panel)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(6)
        main_layout.addWidget(self.view_grid_widget, 1)

        timeline_group = QtWidgets.QGroupBox("Timeline")
        timeline = QtWidgets.QHBoxLayout(timeline_group)
        timeline.setContentsMargins(8, 8, 8, 8)
        self.play_button = QtWidgets.QPushButton("Play")
        self.step_button = QtWidgets.QPushButton("Step")
        self.time_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.time_slider.setRange(0, 1000)
        self.time_slider.setTracking(False)
        self.time_slider.valueChanged.connect(self._on_slider_changed)
        self.time_input = QtWidgets.QDoubleSpinBox()
        self.time_input.setRange(0.0, 1_000_000.0)
        self.time_input.setDecimals(3)
        self.time_input.valueChanged.connect(self._on_time_input_changed)
        self.time_input.setMaximumWidth(120)
        self.rate_box = QtWidgets.QComboBox()
        self.rate_box.addItems(["0.25x", "0.5x", "1x", "2x", "4x"])
        self.rate_box.setCurrentText("1x")
        self.rate_box.setMaximumWidth(90)
        self.rate_box.currentTextChanged.connect(self._on_playback_rate_changed)
        timeline.addWidget(self.play_button)
        timeline.addWidget(self.step_button)
        timeline.addWidget(self.time_slider, 1)
        timeline.addWidget(QtWidgets.QLabel("Time s"))
        timeline.addWidget(self.time_input)
        timeline.addWidget(QtWidgets.QLabel("Rate"))
        timeline.addWidget(self.rate_box)
        main_layout.addWidget(timeline_group)

        output_panel = QtWidgets.QWidget()
        output_layout = QtWidgets.QVBoxLayout(output_panel)
        output_layout.setContentsMargins(8, 8, 8, 8)
        output_layout.setSpacing(6)
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Ready")
        output_layout.addWidget(self.progress_bar)
        self.log_text = QtWidgets.QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(100)
        output_layout.addWidget(self.log_text, 1)

        self.preview_timer = QtCore.QTimer()
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(50)
        self.preview_timer.timeout.connect(self._update_preview)
        self.play_timer = QtCore.QTimer()
        self.play_timer.setInterval(int(1000 / self._playback_fps))
        self.play_timer.timeout.connect(self._advance_playback)
        self.play_button.clicked.connect(self._toggle_playback)
        self.step_button.clicked.connect(self._step_forward)

        self.topic_dock = self._make_dock(
            "Topic list",
            self.topic_tree,
            QtCore.Qt.DockWidgetArea.LeftDockWidgetArea,
        )
        self.main_view_dock = self._make_dock(
            "Main view",
            main_panel,
            QtCore.Qt.DockWidgetArea.RightDockWidgetArea,
        )
        self.properties_dock = self._make_dock(
            "Properties",
            settings_scroll,
            QtCore.Qt.DockWidgetArea.RightDockWidgetArea,
        )
        self.output_dock = self._make_dock(
            "Output",
            output_panel,
            QtCore.Qt.DockWidgetArea.BottomDockWidgetArea,
        )
        self.window.splitDockWidget(
            self.main_view_dock,
            self.properties_dock,
            QtCore.Qt.Orientation.Horizontal,
        )
        self._autosize_docks()

    def _build_menus(self) -> None:
        menu_bar = self.window.menuBar()
        menu = menu_bar.addMenu("File")
        self._file_menu = menu
        import_action = self.QtGui.QAction("Import bag...", self.window)
        export_action = self.QtGui.QAction("Export...", self.window)
        version_action = self.QtGui.QAction("Version...", self.window)
        self._file_actions = [import_action, export_action, version_action]
        import_action.triggered.connect(self._import_bag)
        export_action.triggered.connect(self._show_export_dialog)
        version_action.triggered.connect(self._show_version_dialog)
        menu.addAction(import_action)
        menu.addAction(export_action)
        menu.addSeparator()
        menu.addAction(version_action)
        self._windows_menu = menu_bar.addMenu("Windows")

    def _make_dock(self, title: str, widget: Any, area: Any) -> Any:
        dock = self.QtWidgets.QDockWidget(title, self.window)
        dock.setObjectName(title.replace(" ", "_").lower())
        dock.setWidget(widget)
        dock.setAllowedAreas(
            self.QtCore.Qt.DockWidgetArea.LeftDockWidgetArea
            | self.QtCore.Qt.DockWidgetArea.RightDockWidgetArea
            | self.QtCore.Qt.DockWidgetArea.TopDockWidgetArea
            | self.QtCore.Qt.DockWidgetArea.BottomDockWidgetArea
        )
        dock.setFeatures(
            self.QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetClosable
            | self.QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetMovable
            | self.QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.window.addDockWidget(area, dock)
        self._dock_widgets[title] = dock
        if self._windows_menu is not None:
            action = dock.toggleViewAction()
            action.setText(title)
            self._windows_menu.addAction(action)
        dock.visibilityChanged.connect(lambda _visible: self._queue_autosize_docks())
        return dock

    def _new_pane(self, parent: Any | None = None) -> Any:
        pane = self.TopicViewPane(self, parent)
        pane.set_view_title(f"View {self._next_view_id}")
        self._next_view_id += 1
        return pane

    def _layout_panes(self) -> None:
        while self.view_grid.count():
            item = self.view_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        for index, pane in enumerate(self._panes):
            row = index // self._grid_cols
            column = index % self._grid_cols
            self.view_grid.addWidget(pane, row, column)
            pane.setVisible(self._maximized_pane is None or pane is self._maximized_pane)
        self._queue_autosize_docks()

    def _queue_autosize_docks(self) -> None:
        self.QtCore.QTimer.singleShot(0, self._autosize_docks)

    def _autosize_docks(self) -> None:
        visible_docks = [
            dock for dock in [
                getattr(self, "topic_dock", None),
                getattr(self, "main_view_dock", None),
                getattr(self, "properties_dock", None),
            ]
            if dock is not None and dock.isVisible()
        ]
        if len(visible_docks) >= 2:
            widths = []
            for dock in visible_docks:
                if dock is getattr(self, "main_view_dock", None):
                    widths.append(max(520, int(self.window.width() * 0.58)))
                else:
                    widths.append(260)
            self.window.resizeDocks(
                visible_docks,
                widths,
                self.QtCore.Qt.Orientation.Horizontal,
            )
        output_dock = getattr(self, "output_dock", None)
        if output_dock is not None and output_dock.isVisible():
            self.window.resizeDocks(
                [output_dock],
                [max(140, int(self.window.height() * 0.20))],
                self.QtCore.Qt.Orientation.Vertical,
            )

    def _populate_topics(self) -> None:
        self.topic_tree.clear()
        self._topic_by_item.clear()
        self._topic_info_by_name = {topic.name: topic for topic in self.session.list_topics()}
        nodes: dict[tuple[str, ...], Any] = {}
        for topic in self.session.list_topics():
            parts = [part for part in topic.name.split("/") if part]
            parent = None
            for depth, part in enumerate(parts):
                key = tuple(parts[: depth + 1])
                item = nodes.get(key)
                if item is None:
                    is_leaf = depth == len(parts) - 1
                    item = self.QtWidgets.QTreeWidgetItem([
                        part,
                        topic.category if is_leaf else "",
                        str(topic.message_count) if is_leaf else "",
                    ])
                    flags = item.flags()
                    if is_leaf:
                        flags |= self.QtCore.Qt.ItemFlag.ItemIsDragEnabled
                        item.setData(0, self.QtCore.Qt.ItemDataRole.UserRole, topic.name)
                    item.setFlags(flags)
                    if parent is None:
                        self.topic_tree.addTopLevelItem(item)
                    else:
                        parent.addChild(item)
                    nodes[key] = item
                parent = item
            if parent is not None:
                parent.setCheckState(0, self.QtCore.Qt.CheckState.Unchecked)
                parent.setToolTip(0, topic.name)
                parent.setData(0, self.QtCore.Qt.ItemDataRole.UserRole, topic.name)
                self._topic_by_item[id(parent)] = topic.name
        self.topic_tree.collapseAll()
        self._autosize_topic_columns()

    def _autosize_topic_columns(self) -> None:
        for column in range(self.topic_tree.columnCount()):
            self.topic_tree.resizeColumnToContents(column)

    def _load_metadata_time_bounds(self) -> None:
        reader = self.session.reader
        if reader is None:
            return
        try:
            self._bag_start_ns, self._bag_end_ns = reader.get_time_bounds()
        except Exception:
            self._bag_start_ns, self._bag_end_ns = None, None
        if self._bag_start_ns is not None and self._bag_end_ns is not None:
            duration = max(0.0, (self._bag_end_ns - self._bag_start_ns) / 1e9)
            self.time_input.setRange(0.0, duration)

    def _on_topic_selection_changed(self) -> None:
        topic = self._selected_topic()
        if topic is None:
            return
        self._apply_topic_settings(topic)
        if self._active_pane is not None:
            self.assign_topic_to_pane(self._active_pane, topic)

    def _on_topic_double_clicked(self, item: Any, _column: int) -> None:
        topic = item.data(0, self.QtCore.Qt.ItemDataRole.UserRole)
        if topic and self._active_pane is not None:
            self.assign_topic_to_pane(self._active_pane, str(topic))

    def _apply_topic_settings(self, topic: str) -> None:
        settings = self.settings.topics.get(topic)
        if settings is None:
            return
        self.visible_check.setChecked(settings.visible)
        self.point_size.setValue(settings.point_size)
        self.decimation.setValue(settings.decimation)
        self.opacity.setValue(settings.opacity)
        self.sync_offset.setValue(settings.sync_offset_sec)

    def _on_time_input_changed(self, value: float) -> None:
        if self.time_slider.hasFocus():
            return
        maximum = max(1.0, self.time_input.maximum())
        self.time_slider.blockSignals(True)
        self.time_slider.setValue(int((value / maximum) * self.time_slider.maximum()))
        self.time_slider.blockSignals(False)
        self._request_preview_update()

    def _on_slider_changed(self, value: int) -> None:
        maximum = max(1.0, self.time_input.maximum())
        seconds = (value / max(1, self.time_slider.maximum())) * maximum
        self.time_input.blockSignals(True)
        self.time_input.setValue(seconds)
        self.time_input.blockSignals(False)
        self._request_preview_update()

    def _on_playback_rate_changed(self, text: str) -> None:
        try:
            self._playback_rate = float(text.rstrip("x"))
        except ValueError:
            self._playback_rate = 1.0

    def _request_preview_update(self) -> None:
        if self.play_timer.isActive():
            self.preview_timer.stop()
            self._update_preview()
            return
        self.preview_timer.start()

    def _toggle_playback(self) -> None:
        if self.play_timer.isActive():
            self.play_timer.stop()
            self.play_button.setText("Play")
            self.time_slider.setTracking(False)
            return
        if not self._prepare_image_playback():
            return
        self.play_button.setText("Pause")
        self.time_slider.setTracking(True)
        self.preview_timer.stop()
        self._update_preview()
        self.play_timer.start()

    def _prepare_image_playback(self) -> bool:
        image_panes = [
            pane for pane in self._all_panes()
            if pane.isVisible() and pane.is_image_topic()
        ]
        if not image_panes:
            self._request_preview_update()
            return True
        for pane in image_panes:
            if not pane.ensure_rendered_for_playback():
                self._log(f"Playback render was cancelled for {pane.topic}.")
                return False
        return True

    def _advance_playback(self) -> None:
        next_time = self.time_input.value() + ((1.0 / self._playback_fps) * self._playback_rate)
        reached_end = False
        if next_time >= self.time_input.maximum():
            next_time = self.time_input.maximum()
            reached_end = True
        self._set_timeline_seconds(next_time, immediate=True)
        if reached_end:
            self.play_timer.stop()
            self.play_button.setText("Play")
            self.time_slider.setTracking(False)

    def _step_forward(self) -> None:
        self._set_timeline_seconds(
            min(self.time_input.maximum(), self.time_input.value() + (1.0 / self._playback_fps)),
            immediate=True,
        )

    def _set_timeline_seconds(self, seconds: float, *, immediate: bool) -> None:
        maximum = max(1.0, self.time_input.maximum())
        self.time_input.blockSignals(True)
        self.time_input.setValue(seconds)
        self.time_input.blockSignals(False)
        self.time_slider.blockSignals(True)
        self.time_slider.setValue(int((seconds / maximum) * self.time_slider.maximum()))
        self.time_slider.blockSignals(False)
        if immediate:
            self._update_preview()
        else:
            self._request_preview_update()

    def _selected_topic(self) -> str | None:
        items = self.topic_tree.selectedItems()
        if not items:
            return None
        return self._topic_by_item.get(id(items[0]))

    def _current_timestamp_ns(self) -> int | None:
        if self._bag_start_ns is None:
            return None
        seconds = self.time_input.value()
        return self._bag_start_ns + int(seconds * 1e9)

    def _update_preview(self) -> None:
        timestamp_ns = self._current_timestamp_ns()
        if self.preview is None or timestamp_ns is None:
            return
        for pane in self._all_panes():
            if pane.isVisible():
                pane.show_at_timestamp(timestamp_ns)

    def _maybe_offer_startup_update_check(self) -> None:
        mode = str(self._update_settings.value("updates/mode", "") or "")
        if mode not in {"check", "auto", "off"}:
            mode = self._ask_update_preference()
            self._update_settings.setValue("updates/mode", mode)
        if mode == "off":
            return
        info = self._check_for_updates(show_no_update=False)
        if info is None or not info.update_available:
            return
        if mode == "auto":
            self._run_upgrade_from_gui(info, automatic=True)
        else:
            self._show_version_dialog(info)

    def _ask_update_preference(self) -> str:
        box = self.QtWidgets.QMessageBox(self.window)
        box.setWindowTitle("Update checker")
        box.setIcon(self.QtWidgets.QMessageBox.Icon.Question)
        box.setText("How should ros2unbag check for updates on startup?")
        box.setInformativeText(
            "The checker contacts the GitHub release API. You can change this later "
            "from File > Version."
        )
        auto_button = box.addButton("Auto update", self.QtWidgets.QMessageBox.ButtonRole.AcceptRole)
        check_button = box.addButton("Check only", self.QtWidgets.QMessageBox.ButtonRole.YesRole)
        off_button = box.addButton("Turn off", self.QtWidgets.QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(check_button)
        box.exec()
        clicked = box.clickedButton()
        if clicked is auto_button:
            return "auto"
        if clicked is off_button:
            return "off"
        return "check"

    def _show_version_dialog(self, update_info: UpdateInfo | None = None) -> None:
        dialog = self.QtWidgets.QDialog(self.window)
        dialog.setWindowTitle("ros2unbag version")
        dialog.resize(720, 560)
        layout = self.QtWidgets.QVBoxLayout(dialog)

        current_label = self.QtWidgets.QLabel(f"Current version: {current_version()}")
        current_label.setStyleSheet("font-weight: 600;")
        status_label = self.QtWidgets.QLabel()
        status_label.setWordWrap(True)
        notes = self.QtWidgets.QTextEdit()
        notes.setReadOnly(True)
        notes.setPlainText(_local_changelog_text())
        layout.addWidget(current_label)
        layout.addWidget(status_label)
        layout.addWidget(notes, 1)

        preference_row = self.QtWidgets.QHBoxLayout()
        preference_row.addWidget(self.QtWidgets.QLabel("Startup updates"))
        preference_box = self.QtWidgets.QComboBox()
        preference_box.addItem("Check only", "check")
        preference_box.addItem("Auto update", "auto")
        preference_box.addItem("Off", "off")
        stored_mode = str(self._update_settings.value("updates/mode", "check") or "check")
        index = preference_box.findData(stored_mode)
        preference_box.setCurrentIndex(max(0, index))
        preference_box.currentIndexChanged.connect(
            lambda _index: self._update_settings.setValue(
                "updates/mode", preference_box.currentData()
            )
        )
        preference_row.addWidget(preference_box)
        preference_row.addStretch(1)
        layout.addLayout(preference_row)

        buttons = self.QtWidgets.QDialogButtonBox(
            self.QtWidgets.QDialogButtonBox.StandardButton.Close
        )
        check_button = self.QtWidgets.QPushButton("Check update")
        upgrade_button = self.QtWidgets.QPushButton("Upgrade")
        buttons.addButton(check_button, self.QtWidgets.QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(upgrade_button, self.QtWidgets.QDialogButtonBox.ButtonRole.ActionRole)
        layout.addWidget(buttons)

        def apply_info(info: UpdateInfo | None) -> None:
            upgrade_button.setEnabled(bool(info and info.update_available and info.latest_ref))
            if info is None:
                status_label.setText("Local changelog is shown below.")
                return
            self._latest_update_info = info
            if info.error:
                status_label.setText(f"Update check failed: {info.error}")
                return
            latest = info.latest_ref or info.latest_version or "unknown"
            if info.update_available:
                status_label.setText(
                    f"New version available: {latest} "
                    f"(installed {info.current_version})."
                )
                notes.setPlainText(info.changes or "No release notes were provided.")
            else:
                status_label.setText(
                    f"No newer version found. Latest: {latest}; "
                    f"installed: {info.current_version}."
                )

        def check_now() -> None:
            apply_info(self._check_for_updates(show_no_update=True, parent=dialog))

        def upgrade_now() -> None:
            if self._latest_update_info is not None:
                self._run_upgrade_from_gui(self._latest_update_info, parent=dialog)

        check_button.clicked.connect(check_now)
        upgrade_button.clicked.connect(upgrade_now)
        buttons.rejected.connect(dialog.reject)
        apply_info(update_info)
        dialog.exec()

    def _check_for_updates(
        self,
        *,
        show_no_update: bool,
        parent: Any | None = None,
    ) -> UpdateInfo | None:
        progress = self.QtWidgets.QProgressDialog(
            "Checking for ros2unbag updates...",
            None,
            0,
            0,
            parent or self.window,
        )
        progress.setWindowModality(self.QtCore.Qt.WindowModality.WindowModal)
        progress.show()
        self.QtWidgets.QApplication.processEvents()
        try:
            info = check_for_update()
        finally:
            progress.close()
        self._latest_update_info = info
        if info.error:
            if show_no_update:
                self._show_warning(f"Update check failed: {info.error}")
            return info
        if info.update_available:
            return info
        if show_no_update:
            latest = info.latest_ref or info.latest_version or "unknown"
            self.QtWidgets.QMessageBox.information(
                parent or self.window,
                "ros2unbag update",
                f"No newer version found.\nLatest: {latest}\nInstalled: {info.current_version}",
            )
        return info

    def _run_upgrade_from_gui(
        self,
        info: UpdateInfo,
        *,
        parent: Any | None = None,
        automatic: bool = False,
    ) -> None:
        if not info.latest_ref:
            self._show_warning("No upgrade target was found. Run Check update first.")
            return
        if not automatic:
            answer = self.QtWidgets.QMessageBox.question(
                parent or self.window,
                "Upgrade ros2unbag",
                f"Upgrade ros2unbag to {info.latest_ref}?\n\n"
                "The application should be restarted after upgrade.",
                self.QtWidgets.QMessageBox.StandardButton.Yes
                | self.QtWidgets.QMessageBox.StandardButton.No,
            )
            if answer != self.QtWidgets.QMessageBox.StandardButton.Yes:
                return
        progress = self.QtWidgets.QProgressDialog(
            f"Upgrading ros2unbag to {info.latest_ref}...",
            None,
            0,
            0,
            parent or self.window,
        )
        progress.setWindowModality(self.QtCore.Qt.WindowModality.WindowModal)
        progress.show()
        self.QtWidgets.QApplication.processEvents()
        try:
            run_upgrade(build_upgrade_plan(ref=info.latest_ref))
        except Exception as exc:
            self._show_warning(f"Upgrade failed: {exc}")
            return
        finally:
            progress.close()
        self.QtWidgets.QMessageBox.information(
            parent or self.window,
            "Upgrade complete",
            "Upgrade finished. Restart ros2unbag to use the updated code.",
        )

    def _import_bag(self) -> None:
        path = self.QtWidgets.QFileDialog.getExistingDirectory(
            self.window, "Select ROS bag folder"
        )
        if path:
            self.open_bag(path)

    def _show_export_dialog(self) -> None:
        if self.session.reader is None:
            self._show_warning("Open or import a bag before exporting.")
            return
        dialog = self.QtWidgets.QDialog(self.window)
        dialog.setWindowTitle("Export topics")
        dialog.resize(760, 520)
        layout = self.QtWidgets.QVBoxLayout(dialog)

        topic_list = self.QtWidgets.QListWidget()
        topic_list.setSelectionMode(self.QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        for topic in self.session.list_topics():
            item = self.QtWidgets.QListWidgetItem(f"{topic.name}  [{topic.category}]")
            item.setData(self.QtCore.Qt.ItemDataRole.UserRole, topic.name)
            item.setCheckState(self.QtCore.Qt.CheckState.Unchecked)
            topic_list.addItem(item)
        active_topic = self._active_pane.topic if self._active_pane is not None else None
        if active_topic is not None:
            for index in range(topic_list.count()):
                item = topic_list.item(index)
                if item.data(self.QtCore.Qt.ItemDataRole.UserRole) == active_topic:
                    item.setCheckState(self.QtCore.Qt.CheckState.Checked)
                    break
        layout.addWidget(topic_list, 1)

        form = self.QtWidgets.QFormLayout()
        format_box = self.QtWidgets.QComboBox()
        out_row = self.QtWidgets.QHBoxLayout()
        out_edit = self.QtWidgets.QLineEdit()
        browse_button = self.QtWidgets.QPushButton("Browse")
        out_row.addWidget(out_edit, 1)
        out_row.addWidget(browse_button)
        fps_box = self.QtWidgets.QDoubleSpinBox()
        fps_box.setRange(1.0, 240.0)
        fps_box.setValue(30.0)
        fps_box.setDecimals(1)
        summary_label = self.QtWidgets.QLabel()
        summary_label.setWordWrap(True)
        form.addRow("Format", format_box)
        form.addRow("Output directory", out_row)
        form.addRow("MP4 FPS", fps_box)
        form.addRow("Summary", summary_label)
        layout.addLayout(form)

        buttons = self.QtWidgets.QDialogButtonBox(
            self.QtWidgets.QDialogButtonBox.StandardButton.Cancel
            | self.QtWidgets.QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(self.QtWidgets.QDialogButtonBox.StandardButton.Ok).setText("Export")
        layout.addWidget(buttons)

        def selected_topics() -> list[str]:
            return [
                str(topic_list.item(index).data(self.QtCore.Qt.ItemDataRole.UserRole))
                for index in range(topic_list.count())
                if topic_list.item(index).checkState() == self.QtCore.Qt.CheckState.Checked
            ]

        def refresh_formats() -> None:
            topics = selected_topics()
            current = format_box.currentText()
            format_box.clear()
            if not topics:
                summary_label.setText("Select one or more topics.")
                return
            common: set[str] | None = None
            for topic_name in topics:
                info = self._topic_info_by_name[topic_name]
                formats = set(compatible_export_formats(info))
                common = formats if common is None else common & formats
            values = sorted(common or [])
            format_box.addItems(values)
            if current in values:
                format_box.setCurrentText(current)
            refresh_summary()

        def refresh_summary() -> None:
            topics = selected_topics()
            fmt = format_box.currentText() or "(format)"
            out_dir = out_edit.text().strip() or "(output directory)"
            summary_label.setText(
                f"Export {len(topics)} topic(s) as {fmt} to {out_dir}."
            )

        def browse_output() -> None:
            out_dir = self.QtWidgets.QFileDialog.getExistingDirectory(
                dialog, "Select export directory"
            )
            if out_dir:
                out_edit.setText(out_dir)
                refresh_summary()

        def run_export() -> None:
            topics = selected_topics()
            fmt = format_box.currentText()
            out_dir = out_edit.text().strip()
            if not topics or not fmt or not out_dir:
                self._show_warning("Select at least one topic, a format, and an output directory.")
                return
            selections: list[ExportSelection] = []
            try:
                for topic_name in topics:
                    selections.append(
                        self.session.prepare_export_selection(
                            topic_name,
                            fmt,
                            out_dir,
                            fps=fps_box.value(),
                        )
                    )
            except Exception as exc:
                self._show_warning(str(exc))
                return
            question = (
                f"Export {len(selections)} topic(s) as {fmt} to:\n{out_dir}\n\n"
                + "\n".join(selection.topic for selection in selections[:12])
            )
            if len(selections) > 12:
                question += f"\n...and {len(selections) - 12} more"
            answer = self.QtWidgets.QMessageBox.question(
                dialog,
                "Confirm export",
                question,
                self.QtWidgets.QMessageBox.StandardButton.Yes
                | self.QtWidgets.QMessageBox.StandardButton.No,
            )
            if answer != self.QtWidgets.QMessageBox.StandardButton.Yes:
                return

            progress = self.QtWidgets.QProgressDialog(
                "Exporting selected topics...",
                "Cancel",
                0,
                len(selections),
                dialog,
            )
            progress.setWindowModality(self.QtCore.Qt.WindowModality.WindowModal)
            results = []
            for index, selection in enumerate(selections, start=1):
                if progress.wasCanceled():
                    break
                progress.setLabelText(f"Exporting {selection.topic} as {selection.format}")
                progress.setValue(index - 1)
                self._start_progress(f"Exporting {selection.topic}", None)
                self.QtWidgets.QApplication.processEvents()
                try:
                    results.append(
                        self.session.export_topic(
                            selection.topic,
                            selection.format,
                            selection.out_dir,
                            fps=selection.fps,
                            progress_factory=lambda description, total: _GuiProgressContext(
                                self,
                                progress,
                                description,
                                total,
                            ),
                        )
                    )
                except Exception as exc:
                    self._log(f"Export failed for {selection.topic}: {exc}")
                finally:
                    self._set_progress(
                        f"Finished {index}/{len(selections)} export(s)",
                        index,
                        len(selections),
                    )
            progress.setValue(len(selections))
            self._finish_progress()
            self._log(f"Exported {len(results)} topic(s) to {out_dir}")
            dialog.accept()

        topic_list.itemChanged.connect(lambda _item: refresh_formats())
        format_box.currentTextChanged.connect(lambda _text: refresh_summary())
        out_edit.textChanged.connect(lambda _text: refresh_summary())
        browse_button.clicked.connect(browse_output)
        buttons.accepted.connect(run_export)
        buttons.rejected.connect(dialog.reject)
        refresh_formats()
        dialog.exec()

    def _save_sidecar(self) -> None:
        bag_path = Path(self.settings.bag_path) if self.settings.bag_path else Path.cwd()
        output_path = (
            bag_path / "ros2unbag_session.json"
            if bag_path.is_dir()
            else bag_path.with_name("ros2unbag_session.json")
        )
        save_preview_settings(self.settings, output_path)
        self._log(f"Saved {output_path}")

    def _all_panes(self) -> list[Any]:
        return [*self._panes, *self._popout_panes]

    def _start_progress(self, label: str, total: int | None) -> None:
        self.progress_bar.setTextVisible(True)
        if total is None or total <= 0:
            self.progress_bar.setRange(0, 0)
            self.progress_bar.setFormat(label)
        else:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat(f"{label} 0/{total}")
        self.QtWidgets.QApplication.processEvents()

    def _set_progress(self, label: str, value: int, total: int | None) -> None:
        if total is None or total <= 0:
            self.progress_bar.setRange(0, 0)
            self.progress_bar.setFormat(f"{label} {value}")
        else:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(min(value, total))
            self.progress_bar.setFormat(f"{label} {min(value, total)}/{total}")
        self.QtWidgets.QApplication.processEvents()

    def _finish_progress(self, label: str = "Ready") -> None:
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(label)
        self.QtWidgets.QApplication.processEvents()

    def _show_warning(self, message: str) -> None:
        self.QtWidgets.QMessageBox.warning(self.window, "ros2unbag", message)
        self._log(message)

    def _log(self, message: str) -> None:
        self.log_text.append(message)


def run_gui(bag_path: str | Path | None = None) -> None:
    _QtCore, _QtGui, QtWidgets = _require_pyside6()
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    viewer = TimelineViewer(bag_path)
    viewer.show()
    app.exec()


class _GuiProgressContext:
    def __init__(
        self,
        owner: TimelineViewer,
        progress_dialog: Any,
        description: str,
        total: int | None,
    ) -> None:
        self.owner = owner
        self.progress_dialog = progress_dialog
        self.description = description
        self.total = total
        self.count = 0
        self._last_update = 0.0

    def __enter__(self) -> Any:
        self.owner._start_progress(self.description, self.total)
        if self.total is None or self.total <= 0:
            self.progress_dialog.setRange(0, 0)
        else:
            self.progress_dialog.setRange(0, self.total)
            self.progress_dialog.setValue(0)
        self.progress_dialog.setLabelText(self.description)
        return self._advance

    def __exit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        self.owner._finish_progress()

    def _advance(self, amount: int) -> None:
        self.count += amount
        now = perf_counter()
        if (
            self.count == 1
            or self.total is not None and self.count >= self.total
            or now - self._last_update >= 0.05
        ):
            self._last_update = now
            self.owner._set_progress(self.description, self.count, self.total)
            if self.total is None or self.total <= 0:
                self.progress_dialog.setRange(0, 0)
            else:
                self.progress_dialog.setRange(0, self.total)
                self.progress_dialog.setValue(min(self.count, self.total))
            self.progress_dialog.setLabelText(
                f"{self.description} ({self.count}"
                + (f"/{self.total})" if self.total else ")")
            )
            self.owner.QtWidgets.QApplication.processEvents()
            if self.progress_dialog.wasCanceled():
                raise RuntimeError("Operation cancelled")


def _create_topic_tree_class(QtWidgets: Any, QtCore: Any) -> type:
    class TopicTreeWidget(QtWidgets.QTreeWidget):
        def mimeData(self, items: list[Any]) -> Any:
            mime = QtCore.QMimeData()
            for item in items:
                topic = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
                if topic:
                    text = str(topic)
                    mime.setData(TOPIC_MIME, text.encode("utf-8"))
                    mime.setText(text)
                    break
            return mime

    return TopicTreeWidget


def _create_view_pane_class(QtWidgets: Any, QtCore: Any, QtGui: Any) -> type:
    class TopicViewPane(QtWidgets.QFrame):
        def __init__(self, owner: TimelineViewer, parent: Any | None = None) -> None:
            super().__init__(parent)
            self.owner = owner
            self.view_title = "View"
            self.topic: str | None = None
            self.topic_info: TopicInfo | None = None
            self.rendered_frames: list[RenderedFrame] = []
            self.rendered_timestamps: list[int] = []
            self.rendered_size: tuple[int, int] | None = None
            self.setAcceptDrops(True)
            self.setObjectName("topicViewPane")
            self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)

            layout = QtWidgets.QVBoxLayout(self)
            layout.setContentsMargins(6, 6, 6, 6)
            layout.setSpacing(2)
            top_bar = QtWidgets.QHBoxLayout()
            top_bar.setContentsMargins(0, 0, 0, 0)
            self.title_label = QtWidgets.QLabel("Drop topic here")
            self.title_label.setStyleSheet("font-weight: 600;")
            self.render_button = QtWidgets.QToolButton()
            self.render_button.setText("Render")
            self.max_button = QtWidgets.QToolButton()
            self.max_button.setText("Max")
            self.pop_button = QtWidgets.QToolButton()
            self.pop_button.setText("Pop")
            self.delete_button = QtWidgets.QToolButton()
            self.delete_button.setText("X")
            top_bar.addWidget(self.title_label, 1)
            top_bar.addWidget(self.render_button)
            top_bar.addWidget(self.max_button)
            top_bar.addWidget(self.pop_button)
            top_bar.addWidget(self.delete_button)
            layout.addLayout(top_bar)

            self.stack = QtWidgets.QStackedWidget()
            self.image_label = QtWidgets.QLabel("Drop an image topic or select a topic.")
            self.image_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.image_label.setMinimumSize(320, 220)
            self.point_renderer = create_point_cloud_renderer(QtWidgets)
            self.point_widget = self.point_renderer.widget()
            self.raw_text = QtWidgets.QTextEdit()
            self.raw_text.setReadOnly(True)
            self.stack.addWidget(self.image_label)
            self.stack.addWidget(self.point_widget)
            self.stack.addWidget(self.raw_text)
            layout.addWidget(self.stack, 1)

            self.render_button.clicked.connect(lambda: self.ensure_rendered_for_playback())
            self.max_button.clicked.connect(lambda: self.owner.toggle_maximize_pane(self))
            self.pop_button.clicked.connect(lambda: self.owner.popout_pane(self))
            self.delete_button.clicked.connect(lambda: self.owner.delete_pane(self))

        def set_view_title(self, title: str) -> None:
            self.view_title = title
            self._refresh_title()

        def clear_topic(self) -> None:
            self.topic = None
            self.topic_info = None
            self.rendered_frames.clear()
            self.rendered_timestamps.clear()
            self.rendered_size = None
            self._refresh_title()
            self.image_label.clear()
            self.image_label.setText("Drop an image topic or select a topic.")
            self.raw_text.clear()

        def set_topic(self, topic: str, topic_info: TopicInfo) -> None:
            self.topic = topic
            self.topic_info = topic_info
            self.rendered_frames.clear()
            self.rendered_timestamps.clear()
            self.rendered_size = None
            self._refresh_title()
            self.title_label.setToolTip(topic)
            self.raw_text.setPlainText(f"{topic}\n{topic_info.msgtype}\n{topic_info.category}")

        def _refresh_title(self) -> None:
            if self.topic is None:
                self.title_label.setText(f"{self.view_title}: Drop topic here")
                self.title_label.setToolTip("")
                return
            leaf = self.topic.rsplit("/", 1)[-1]
            category = self.topic_info.category if self.topic_info is not None else "topic"
            self.title_label.setText(f"{self.view_title}: {leaf}")
            self.title_label.setToolTip(f"{self.topic}\n{category}")

        def is_image_topic(self) -> bool:
            return _is_image_topic(self.topic_info)

        def ensure_rendered_for_playback(self) -> bool:
            if self.topic is None or self.topic_info is None:
                self.owner._log("Assign an image topic to this view before rendering.")
                return False
            if not self.is_image_topic():
                self.owner._show_warning("Only image-compatible topics can be rendered for playback.")
                return False
            current_size = _usable_label_size(self.image_label)
            if self.rendered_frames and self.rendered_size == current_size:
                return True

            reader = self.owner.session.reader
            if reader is None:
                return False
            self.rendered_frames.clear()
            self.rendered_timestamps.clear()
            self.rendered_size = current_size
            total = self.topic_info.message_count if self.topic_info.message_count > 0 else 0
            self.owner._start_progress(f"Rendering {self.topic}", total if total > 0 else None)
            progress = QtWidgets.QProgressDialog(
                f"Rendering {self.topic} for playback...",
                "Cancel",
                0,
                total,
                self.owner.window,
            )
            if total == 0:
                progress.setRange(0, 0)
            progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
            count = 0
            for record in reader.iter_messages(topics=[self.topic]):
                if progress.wasCanceled():
                    self.rendered_frames.clear()
                    self.rendered_timestamps.clear()
                    self.owner._finish_progress("Render cancelled")
                    return False
                try:
                    frame = _decode_record_frame(record)
                    pixmap = _array_to_scaled_pixmap(
                        QtGui,
                        QtCore,
                        frame.array,
                        current_size,
                    )
                except Exception as exc:
                    self.owner._log(f"Skipped frame at {record.timestamp_ns}: {exc}")
                    continue
                self.rendered_frames.append(
                    RenderedFrame(
                        timestamp_ns=record.timestamp_ns,
                        pixmap=pixmap,
                        width=frame.width,
                        height=frame.height,
                        encoding=frame.encoding,
                    )
                )
                self.rendered_timestamps.append(record.timestamp_ns)
                count += 1
                if count == 1 or count % 10 == 0 or (total > 0 and count >= total):
                    if total > 0:
                        progress.setValue(count)
                    progress.setLabelText(f"Rendered {count} frame(s) for {self.topic}")
                    self.owner._set_progress(
                        f"Rendering {self.topic}",
                        count,
                        total if total > 0 else None,
                    )
            progress.setValue(total if total > 0 else count)
            if not self.rendered_frames:
                self.owner._finish_progress("Ready")
                self.owner._show_warning(f"No frames could be rendered for {self.topic}.")
                return False
            self.owner._log(f"Rendered {len(self.rendered_frames)} frame(s) for {self.topic}.")
            self.show_at_timestamp(self.owner._current_timestamp_ns())
            self.owner._finish_progress()
            return True

        def show_at_timestamp(self, timestamp_ns: int | None) -> None:
            if timestamp_ns is None or self.topic is None or self.topic_info is None:
                return
            if self.rendered_frames:
                self._show_rendered_frame(timestamp_ns)
                return
            preview = self.owner.preview
            if preview is None:
                return
            try:
                if self.is_image_topic():
                    frame = preview.image_preview(self.topic, timestamp_ns)
                    if frame is None:
                        return
                    pixmap = _array_to_scaled_pixmap(
                        QtGui,
                        QtCore,
                        frame.image,
                        _usable_label_size(self.image_label),
                    )
                    self.image_label.setPixmap(pixmap)
                    self.stack.setCurrentWidget(self.image_label)
                elif self.topic_info.category == "point_cloud":
                    cloud = preview.point_cloud_preview(
                        self.topic,
                        timestamp_ns,
                        max_points=max(100, 20_000 // max(1, self.owner.decimation.value())),
                    )
                    if cloud is None:
                        return
                    self.point_renderer.set_points(cloud.points, cloud.color_values)
                    self.stack.setCurrentWidget(self.point_widget)
                else:
                    summary = preview.summary_preview(self.topic, timestamp_ns)
                    self.raw_text.setPlainText(str(summary))
                    self.stack.setCurrentWidget(self.raw_text)
            except Exception as exc:
                self.owner._log(f"Preview error for {self.topic}: {exc}")

        def _show_rendered_frame(self, timestamp_ns: int) -> None:
            index = bisect_left(self.rendered_timestamps, timestamp_ns)
            if index <= 0:
                selected = 0
            elif index >= len(self.rendered_timestamps):
                selected = len(self.rendered_timestamps) - 1
            else:
                before = self.rendered_timestamps[index - 1]
                after = self.rendered_timestamps[index]
                selected = index - 1 if abs(before - timestamp_ns) <= abs(after - timestamp_ns) else index
            frame = self.rendered_frames[selected]
            self.image_label.setPixmap(frame.pixmap)
            self.stack.setCurrentWidget(self.image_label)

        def contextMenuEvent(self, event: Any) -> None:
            menu = QtWidgets.QMenu(self)
            split_horizontal = menu.addAction("Split horizontally")
            split_vertical = menu.addAction("Split vertically")
            menu.addSeparator()
            maximize = menu.addAction("Maximize / restore")
            popout = menu.addAction("Pop out")
            delete = menu.addAction("Delete view")
            action = menu.exec(event.globalPos())
            if action == split_horizontal:
                self.owner.split_pane(self, "horizontal")
            elif action == split_vertical:
                self.owner.split_pane(self, "vertical")
            elif action == maximize:
                self.owner.toggle_maximize_pane(self)
            elif action == popout:
                self.owner.popout_pane(self)
            elif action == delete:
                self.owner.delete_pane(self)

        def dragEnterEvent(self, event: Any) -> None:
            mime = event.mimeData()
            if mime.hasFormat(TOPIC_MIME) or mime.hasText():
                event.acceptProposedAction()
            else:
                event.ignore()

        def dropEvent(self, event: Any) -> None:
            mime = event.mimeData()
            topic = None
            if mime.hasFormat(TOPIC_MIME):
                topic = bytes(mime.data(TOPIC_MIME)).decode("utf-8")
            elif mime.hasText():
                topic = mime.text().strip().splitlines()[0]
            if topic:
                self.owner.assign_topic_to_pane(self, topic)
                event.acceptProposedAction()
            else:
                event.ignore()

        def mousePressEvent(self, event: Any) -> None:
            self.owner._active_pane = self
            super().mousePressEvent(event)

    return TopicViewPane


def _create_drop_window(QtWidgets: Any, QtCore: Any, open_callback: Any) -> Any:
    class DropWindow(QtWidgets.QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setAcceptDrops(True)

        def dragEnterEvent(self, event: Any) -> None:
            if event.mimeData().hasUrls():
                event.acceptProposedAction()
            else:
                event.ignore()

        def dropEvent(self, event: Any) -> None:
            urls = event.mimeData().urls()
            for url in urls:
                if not url.isLocalFile():
                    continue
                open_callback(Path(url.toLocalFile()))
                event.acceptProposedAction()
                return
            event.ignore()

    return DropWindow()


def _require_pyside6() -> tuple[Any, Any, Any]:
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
    except Exception as exc:
        raise RuntimeError(
            "PySide6 is required for the GUI. Install with: py -m pip install -e .[gui]"
        ) from exc
    return QtCore, QtGui, QtWidgets


def _decode_record_frame(record: object) -> Any:
    decoded = getattr(record, "decoded", None)
    if decoded is None:
        raise ValueError("message was not decoded")
    msgtype = str(getattr(record, "msgtype", ""))
    if msgtype == "sensor_msgs/msg/Image":
        return decode_sensor_image(decoded)
    if msgtype == "sensor_msgs/msg/CompressedImage":
        return decode_compressed_image(decoded)
    raise ValueError(f"topic type {msgtype} is not an image type")


def _array_to_scaled_pixmap(QtGui: Any, QtCore: Any, array: Any, size: tuple[int, int]) -> Any:
    pixmap = _qimage_to_pixmap(QtGui, array)
    width, height = size
    return pixmap.scaled(
        width,
        height,
        QtCore.Qt.AspectRatioMode.KeepAspectRatio,
        QtCore.Qt.TransformationMode.FastTransformation,
    )


def _qimage_to_pixmap(QtGui: Any, array: Any) -> Any:
    import cv2
    import numpy as np

    image = array
    if image.dtype != np.uint8:
        image = cv2.normalize(image, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    if image.ndim == 2:
        height, width = image.shape
        qimage = QtGui.QImage(image.data, width, height, width, QtGui.QImage.Format.Format_Grayscale8)
    elif image.ndim == 3 and image.shape[2] == 3:
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        height, width = rgb.shape[:2]
        qimage = QtGui.QImage(rgb.data, width, height, width * 3, QtGui.QImage.Format.Format_RGB888)
    elif image.ndim == 3 and image.shape[2] == 4:
        rgba = cv2.cvtColor(image, cv2.COLOR_BGRA2RGBA)
        height, width = rgba.shape[:2]
        qimage = QtGui.QImage(rgba.data, width, height, width * 4, QtGui.QImage.Format.Format_RGBA8888)
    else:
        raise ValueError(f"Unsupported image shape: {image.shape}")
    return QtGui.QPixmap.fromImage(qimage.copy())


def _usable_label_size(label: Any) -> tuple[int, int]:
    width = max(64, int(label.width() or 640))
    height = max(64, int(label.height() or 480))
    return width, height


def _is_image_topic(topic: TopicInfo | None) -> bool:
    if topic is None:
        return False
    return topic.msgtype in {"sensor_msgs/msg/Image", "sensor_msgs/msg/CompressedImage"} or topic.category in IMAGE_CATEGORIES


def _local_changelog_text() -> str:
    changelog_path = Path(__file__).resolve().parents[2] / "CHANGELOG.md"
    try:
        text = changelog_path.read_text(encoding="utf-8")
    except OSError:
        return "Local changelog was not found in this installation."
    return text[:12_000]
