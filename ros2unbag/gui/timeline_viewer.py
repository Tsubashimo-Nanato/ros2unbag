from __future__ import annotations

from bisect import bisect_left
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from typing import Any

from ros2unbag.core.decoder import decode_compressed_image, decode_sensor_image
from ros2unbag.core.lane_lines import (
    LANE_ROLES,
    LaneOverlayData,
    build_lane_overlay_data,
    lane_role_for_topic,
    lane_topics,
)
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
from ros2unbag.gui.playback import MAX_RENDERED_PLAYBACK_FRAMES, RenderedFrame
from ros2unbag.gui.lane_overlay import create_lane_overlay_panel_class
from ros2unbag.gui.progress import GuiProgressContext as _GuiProgressContext
from ros2unbag.gui.renderers import create_point_cloud_renderer
from ros2unbag.gui.theme import local_changelog_text as _local_changelog_text
from ros2unbag.gui.theme import normalize_theme as _normalize_theme
from ros2unbag.gui.theme import theme_palette as _theme_palette
from ros2unbag.gui.theme import theme_stylesheet as _theme_stylesheet


TOPIC_MIME = "application/x-ros2unbag-topic"
IMAGE_CATEGORIES = {"image", "compressed_image", "mask_candidate"}


class TimelineViewer:
    """Offline bag viewer shell for Windows-first ros2unbag workflows."""

    def __init__(self, bag_path: str | Path | None = None) -> None:
        self.QtCore, self.QtGui, self.QtWidgets = _require_pyside6()
        self.TopicTreeWidget = _create_topic_tree_class(self.QtWidgets, self.QtCore)
        self.TopicViewPane = _create_view_pane_class(
            self.QtWidgets, self.QtCore, self.QtGui
        )
        self.LaneOverlayPanel = create_lane_overlay_panel_class(
            self.QtWidgets,
            self.QtCore,
            self.QtGui,
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
        self._theme_menu: Any | None = None
        self._theme_actions: dict[str, Any] = {}
        self._next_view_id = 1
        self._playback_rate = 1.0
        self._update_settings = self.QtCore.QSettings("TsubashimoNanato", "ros2unbag")
        self._latest_update_info: UpdateInfo | None = None
        stored_theme = str(self._update_settings.value("ui/theme", "") or "")
        self._theme = _normalize_theme(stored_theme) if stored_theme else "dark"
        self._dock_resize_generations = {"horizontal": 0, "vertical": 0}
        self._autosize_pending = False
        self._background_jobs: list[tuple[Any, Any, Any, Any]] = []
        self._lane_topics_by_role: dict[str, TopicInfo] = {}
        self._lane_overlay_data: LaneOverlayData | None = None
        self._lane_load_generation = 0
        self._lane_swap_xy = False

        self.window = _create_drop_window(self.QtWidgets, self.QtCore, self.open_bag)
        self.window.setWindowTitle("ros2unbag Timeline Viewer")
        self.window.resize(1280, 760)
        self._build_ui()
        if bag_path is not None:
            self.open_bag(bag_path)
        self.QtCore.QTimer.singleShot(500, self._maybe_offer_startup_update_check)

    def show(self) -> None:
        self.window.show()
        self._queue_autosize_docks()

    def open_bag(self, bag_path: str | Path) -> None:
        path = Path(bag_path)
        self._log(f"Opening {path}")
        self._clear_lane_overlay()
        self._start_progress(f"Opening {path.name}", None)
        load_dialog = self.QtWidgets.QProgressDialog(
            f"Opening {path}...",
            None,
            0,
            0,
            self.window,
        )
        load_dialog.setWindowTitle("Loading bag")
        load_dialog.setWindowModality(self.QtCore.Qt.WindowModality.WindowModal)
        load_dialog.setMinimumDuration(0)
        load_dialog.show()
        self.QtWidgets.QApplication.processEvents()
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
            self._prepare_lane_overlay(topics)
            self._autosize_topic_columns()
            self._queue_autosize_docks()
            self._log(f"Opened {path} ({len(topics)} topics)")
        except Exception as exc:
            self._show_warning(f"Failed to open bag: {exc}")
        finally:
            load_dialog.close()
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

        self.central_spacer = QtWidgets.QWidget()
        self.central_spacer.setObjectName("centralSpacer")
        self.central_spacer.setMinimumSize(0, 0)
        self.central_spacer.setMaximumWidth(0)
        self.central_spacer.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Ignored,
        )
        self.window.setCentralWidget(self.central_spacer)

        self.topic_tree = self.TopicTreeWidget()
        self.topic_tree.setHeaderLabels(["Topic", "Category", "Count"])
        self.topic_tree.setDragEnabled(True)
        self.topic_tree.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.DragOnly)
        self.topic_tree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.topic_tree.itemSelectionChanged.connect(self._on_topic_selection_changed)
        self.topic_tree.itemDoubleClicked.connect(self._on_topic_double_clicked)
        self.topic_tree.itemChanged.connect(self._on_topic_item_changed)
        self.topic_tree.setMinimumWidth(260)
        self.topic_tree.setRootIsDecorated(True)
        self.topic_tree.setItemsExpandable(True)
        self.topic_tree.setExpandsOnDoubleClick(True)
        self.topic_tree.setIndentation(18)
        self.topic_tree.setUniformRowHeights(True)

        self.topic_panel = QtWidgets.QWidget()
        self.topic_panel.setObjectName("topicPanel")
        topic_layout = QtWidgets.QVBoxLayout(self.topic_panel)
        topic_layout.setContentsMargins(8, 8, 8, 8)
        topic_layout.setSpacing(6)
        topic_toolbar = QtWidgets.QHBoxLayout()
        topic_toolbar.setContentsMargins(0, 0, 0, 0)
        topic_toolbar.setSpacing(6)
        self.topic_search = QtWidgets.QLineEdit()
        self.topic_search.setPlaceholderText("Search topics")
        self.topic_search.setClearButtonEnabled(True)
        self.topic_search.textChanged.connect(self._filter_topic_tree)
        self.topic_expand_button = QtWidgets.QToolButton()
        self.topic_expand_button.setText("Expand")
        self.topic_expand_button.setToolTip("Expand all topic groups")
        self.topic_expand_button.clicked.connect(self._expand_topic_tree)
        self.topic_collapse_button = QtWidgets.QToolButton()
        self.topic_collapse_button.setText("Collapse")
        self.topic_collapse_button.setToolTip("Collapse all topic groups")
        self.topic_collapse_button.clicked.connect(self._collapse_topic_tree)
        topic_toolbar.addWidget(self.topic_search, 1)
        topic_toolbar.addWidget(self.topic_expand_button)
        topic_toolbar.addWidget(self.topic_collapse_button)
        topic_layout.addLayout(topic_toolbar)
        topic_layout.addWidget(self.topic_tree, 1)

        self.view_grid_widget = QtWidgets.QWidget()
        self.view_grid_widget.setObjectName("viewGrid")
        self.view_grid = QtWidgets.QGridLayout(self.view_grid_widget)
        self.view_grid.setContentsMargins(6, 6, 6, 6)
        self.view_grid.setSpacing(6)
        first_pane = self._new_pane()
        self._panes.append(first_pane)
        self._active_pane = first_pane
        self._layout_panes()

        settings_panel = QtWidgets.QWidget()
        settings_panel.setObjectName("propertiesPanel")
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
        settings_scroll.setObjectName("propertiesScroll")
        settings_scroll.viewport().setObjectName("propertiesViewport")
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setWidget(settings_panel)

        self.main_panel = QtWidgets.QWidget()
        self.main_panel.setObjectName("mainPanel")
        main_layout = QtWidgets.QVBoxLayout(self.main_panel)
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
        output_panel.setObjectName("outputPanel")
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

        self.lane_overlay = self.LaneOverlayPanel(
            self.window,
            on_selection_changed=self._on_lane_overlay_selection_changed,
            on_axes_changed=self._set_lane_swap_xy,
        )

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
            self.topic_panel,
            QtCore.Qt.DockWidgetArea.LeftDockWidgetArea,
        )
        self.main_view_dock = self._make_dock(
            "Main view",
            self.main_panel,
            QtCore.Qt.DockWidgetArea.RightDockWidgetArea,
        )
        self.lane_overlay_dock = self._make_dock(
            "Lane line overlay",
            self.lane_overlay,
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
        self.topic_dock.setMinimumWidth(320)
        self.main_view_dock.setMinimumWidth(380)
        self.lane_overlay_dock.setMinimumWidth(300)
        self.lane_overlay_dock.setMinimumHeight(280)
        self.properties_dock.setMinimumWidth(220)
        self.window.splitDockWidget(
            self.main_view_dock,
            self.lane_overlay_dock,
            QtCore.Qt.Orientation.Vertical,
        )
        self.window.splitDockWidget(
            self.main_view_dock,
            self.properties_dock,
            QtCore.Qt.Orientation.Horizontal,
        )
        self._apply_theme()
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
        self._build_theme_menu(menu_bar)
        self._windows_menu = menu_bar.addMenu("Windows")

    def _build_theme_menu(self, menu_bar: Any) -> None:
        theme_menu = menu_bar.addMenu("Theme")
        self._theme_menu = theme_menu
        theme_group = self.QtGui.QActionGroup(self.window)
        theme_group.setExclusive(True)
        bright_action = self.QtGui.QAction("Bright mode", self.window)
        dark_action = self.QtGui.QAction("Dark mode", self.window)
        for theme, action in (("light", bright_action), ("dark", dark_action)):
            action.setCheckable(True)
            action.triggered.connect(lambda _checked=False, value=theme: self._set_theme(value))
            theme_group.addAction(action)
            theme_menu.addAction(action)
            self._theme_actions[theme] = action
        self._sync_theme_actions()

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
        pane.apply_theme(_theme_palette(self._theme))
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
        if self._autosize_pending:
            return
        self._autosize_pending = True

        def run() -> None:
            self._autosize_pending = False
            self._autosize_docks()

        self.QtCore.QTimer.singleShot(0, run)

    def _autosize_docks(self) -> None:
        if not self.window.isVisible():
            return
        self._autosize_topic_columns()
        visible_docks = [
            dock for dock in [
                getattr(self, "topic_dock", None),
                getattr(self, "main_view_dock", None),
                getattr(self, "properties_dock", None),
            ]
            if dock is not None and dock.isVisible()
        ]
        if len(visible_docks) >= 2:
            topic_dock = getattr(self, "topic_dock", None)
            main_dock = getattr(self, "main_view_dock", None)
            properties_dock = getattr(self, "properties_dock", None)
            targets = self._dock_width_targets(
                has_topic=topic_dock in visible_docks,
                has_main=main_dock in visible_docks,
                has_properties=properties_dock in visible_docks,
            )
            widths = []
            for dock in visible_docks:
                if dock is main_dock:
                    widths.append(targets["main"])
                elif dock is topic_dock:
                    widths.append(targets["topic"])
                else:
                    widths.append(targets["properties"])
            self._animate_resize_docks(
                visible_docks,
                widths,
                self.QtCore.Qt.Orientation.Horizontal,
            )
        output_dock = getattr(self, "output_dock", None)
        if output_dock is not None and output_dock.isVisible():
            self._animate_resize_docks(
                [output_dock],
                [max(140, int(self.window.height() * 0.20))],
                self.QtCore.Qt.Orientation.Vertical,
            )

    def _dock_width_targets(
        self,
        *,
        has_topic: bool,
        has_main: bool,
        has_properties: bool,
    ) -> dict[str, int]:
        available = max(640, self.window.width() - 28)
        targets = {
            "topic": self._preferred_topic_width() if has_topic else 0,
            "main": 520 if has_main else 0,
            "properties": 260 if has_properties else 0,
        }
        minimums = {
            "topic": 320 if has_topic else 0,
            "main": 380 if has_main else 0,
            "properties": 220 if has_properties else 0,
        }
        overflow = sum(targets.values()) - available
        for key in ("topic", "properties", "main"):
            if overflow <= 0:
                break
            reducible = max(0, targets[key] - minimums[key])
            reduction = min(overflow, reducible)
            targets[key] -= reduction
            overflow -= reduction
        if overflow < 0 and has_main:
            targets["main"] += abs(overflow)
        return targets

    def _preferred_topic_width(self) -> int:
        columns = self._preferred_topic_column_widths()
        if not columns:
            return 340
        max_width = max(420, int(self.window.width() * 0.38))
        return max(320, min(max_width, sum(columns) + 26))

    def _preferred_topic_column_widths(self) -> list[int]:
        if not hasattr(self, "topic_tree"):
            return []
        topics = self._topic_snapshot()
        metrics = self.topic_tree.fontMetrics()
        topic_width = metrics.horizontalAdvance("Topic") + 36
        category_width = metrics.horizontalAdvance("Category") + 28
        count_width = metrics.horizontalAdvance("Count") + 28
        for topic in topics:
            parts = [part for part in topic.name.split("/") if part]
            if not parts:
                parts = [topic.name]
            for depth, part in enumerate(parts):
                indent = 18 * depth
                topic_width = max(topic_width, indent + metrics.horizontalAdvance(part) + 58)
            category_width = max(category_width, metrics.horizontalAdvance(topic.category or "") + 28)
            count_width = max(count_width, metrics.horizontalAdvance(str(topic.message_count)) + 28)
        topic_width = max(150, min(270, topic_width))
        category_width = max(86, min(120, category_width))
        count_width = max(68, min(76, count_width))
        return [topic_width, category_width, count_width]

    def _topic_snapshot(self) -> list[TopicInfo]:
        if self.session.reader is None:
            return list(self.session.topics)
        try:
            return self.session.list_topics()
        except RuntimeError:
            return list(self.session.topics)

    def _animate_resize_docks(self, docks: list[Any], targets: list[int], orientation: Any) -> None:
        if not docks:
            return
        key = (
            "horizontal"
            if orientation == self.QtCore.Qt.Orientation.Horizontal
            else "vertical"
        )
        self._dock_resize_generations[key] += 1
        generation = self._dock_resize_generations[key]
        starts = [
            dock.width() if orientation == self.QtCore.Qt.Orientation.Horizontal else dock.height()
            for dock in docks
        ]
        steps = 6

        def step(index: int) -> None:
            if generation != self._dock_resize_generations[key]:
                return
            progress = index / steps
            eased = 1.0 - ((1.0 - progress) ** 3)
            values = [
                int(start + ((target - start) * eased))
                for start, target in zip(starts, targets)
            ]
            self.window.resizeDocks(docks, values, orientation)
            if index < steps:
                self.QtCore.QTimer.singleShot(18, lambda: step(index + 1))

        step(1)

    def _populate_topics(self) -> None:
        signals_blocked = self.topic_tree.blockSignals(True)
        try:
            self.topic_tree.clear()
            self._topic_by_item.clear()
            if hasattr(self, "topic_search"):
                self.topic_search.clear()
            topics = self._topic_snapshot()
            self._topic_info_by_name = {topic.name: topic for topic in topics}
            nodes: dict[tuple[str, ...], Any] = {}
            folder_icon = self.window.style().standardIcon(
                self.QtWidgets.QStyle.StandardPixmap.SP_DirIcon
            )
            topic_icon = self.window.style().standardIcon(
                self.QtWidgets.QStyle.StandardPixmap.SP_FileIcon
            )
            for topic in topics:
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
                            item.setIcon(0, topic_icon)
                            item.setData(0, self.QtCore.Qt.ItemDataRole.UserRole, topic.name)
                        else:
                            flags &= ~self.QtCore.Qt.ItemFlag.ItemIsDragEnabled
                            flags &= ~self.QtCore.Qt.ItemFlag.ItemIsSelectable
                            item.setIcon(0, folder_icon)
                            font = item.font(0)
                            font.setBold(True)
                            item.setFont(0, font)
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
        finally:
            self.topic_tree.blockSignals(signals_blocked)
        self._apply_topic_tree_item_styles()
        self._autosize_topic_columns()

    def _apply_topic_tree_item_styles(self) -> None:
        palette = _theme_palette(self._theme)
        muted_brush = self.QtGui.QBrush(self.QtGui.QColor(palette["muted"]))
        text_brush = self.QtGui.QBrush(self.QtGui.QColor(palette["text"]))
        for index in range(self.topic_tree.topLevelItemCount()):
            self._apply_topic_tree_item_style(
                self.topic_tree.topLevelItem(index),
                text_brush,
                muted_brush,
            )

    def _apply_topic_tree_item_style(
        self,
        item: Any,
        text_brush: Any,
        muted_brush: Any,
    ) -> None:
        is_topic = id(item) in self._topic_by_item
        font = item.font(0)
        font.setBold(not is_topic)
        item.setFont(0, font)
        item.setForeground(0, text_brush)
        item.setForeground(1, text_brush if is_topic else muted_brush)
        item.setForeground(2, text_brush if is_topic else muted_brush)
        for index in range(item.childCount()):
            self._apply_topic_tree_item_style(item.child(index), text_brush, muted_brush)

    def _expand_topic_tree(self) -> None:
        self.topic_tree.expandAll()

    def _collapse_topic_tree(self) -> None:
        self.topic_search.clear()
        self.topic_tree.collapseAll()

    def _filter_topic_tree(self, text: str) -> None:
        query = text.strip().lower()
        for index in range(self.topic_tree.topLevelItemCount()):
            item = self.topic_tree.topLevelItem(index)
            self._filter_topic_item(item, query)

    def _filter_topic_item(self, item: Any, query: str) -> bool:
        topic = item.data(0, self.QtCore.Qt.ItemDataRole.UserRole)
        searchable = str(topic or item.text(0)).lower()
        self_matches = not query or query in searchable
        child_matches = False
        for index in range(item.childCount()):
            if self._filter_topic_item(item.child(index), query):
                child_matches = True
        visible = self_matches or child_matches
        item.setHidden(not visible)
        if query:
            item.setExpanded(child_matches)
        return visible

    def _checked_lane_roles(self) -> list[str]:
        checked: set[str] = set()
        for item in self._topic_tree_items():
            if item.checkState(0) != self.QtCore.Qt.CheckState.Checked:
                continue
            topic = item.data(0, self.QtCore.Qt.ItemDataRole.UserRole)
            if not topic:
                continue
            info = self._topic_info_by_name.get(str(topic))
            if info is None:
                continue
            role = lane_role_for_topic(info)
            if role is not None:
                checked.add(role)
        return [role for role in LANE_ROLES if role in checked]

    def _topic_tree_items(self) -> list[Any]:
        items: list[Any] = []

        def collect(item: Any) -> None:
            items.append(item)
            for index in range(item.childCount()):
                collect(item.child(index))

        for index in range(self.topic_tree.topLevelItemCount()):
            collect(self.topic_tree.topLevelItem(index))
        return items

    def _lane_roles_for_view(self, topic_info: TopicInfo | None) -> list[str]:
        if topic_info is None:
            return []
        role = lane_role_for_topic(topic_info)
        if role is None:
            return []
        checked_roles = self._checked_lane_roles()
        if checked_roles:
            return checked_roles
        if hasattr(self, "lane_overlay"):
            visible_roles = self.lane_overlay.visible_roles()
            if visible_roles:
                return visible_roles
        return [role]

    def _refresh_lane_view_panes(self) -> None:
        timestamp_ns = self._current_timestamp_ns()
        for pane in self._all_panes():
            if pane.is_lane_topic():
                pane.show_at_timestamp(timestamp_ns)

    def _set_lane_swap_xy(self, swapped: bool) -> None:
        self._lane_swap_xy = swapped
        if hasattr(self, "lane_overlay"):
            self.lane_overlay.set_swap_xy(swapped)
        for pane in self._all_panes():
            pane.set_lane_swap_xy(swapped)
        self._refresh_lane_view_panes()

    def _autosize_topic_columns(self) -> None:
        widths = self._preferred_topic_column_widths()
        for column, width in enumerate(widths):
            self.topic_tree.setColumnWidth(column, width)
        if hasattr(self, "topic_tree"):
            self.topic_tree.setMinimumWidth(self._preferred_topic_width())

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

    def _clear_lane_overlay(self) -> None:
        self._lane_load_generation += 1
        self._lane_topics_by_role = {}
        self._lane_overlay_data = None
        if hasattr(self, "lane_overlay"):
            self.lane_overlay.set_topics({})
        if hasattr(self, "_panes"):
            self._refresh_lane_view_panes()

    def _prepare_lane_overlay(self, topics: list[TopicInfo]) -> None:
        self._lane_load_generation += 1
        generation = self._lane_load_generation
        self._lane_topics_by_role = lane_topics(topics)
        self._lane_overlay_data = None
        self.lane_overlay.set_topics(self._lane_topics_by_role)
        if not self._lane_topics_by_role:
            return
        self._start_lane_overlay_load(generation)

    def _start_lane_overlay_load(self, generation: int) -> None:
        bag_path = self.session.bag_path
        if bag_path is None:
            return
        backend = self.session.backend
        topics = list(self._lane_topics_by_role.values())
        self.lane_overlay.set_loading()

        def work() -> LaneOverlayData:
            worker_session = Session(backend=backend)
            try:
                worker_session.open_bag(bag_path)
                if worker_session.reader is None:
                    return LaneOverlayData(series_by_role={})
                return build_lane_overlay_data(worker_session.reader, topics)
            finally:
                worker_session.close()

        def handle_success(data: LaneOverlayData) -> None:
            if generation != self._lane_load_generation:
                return
            self._lane_overlay_data = data
            self.lane_overlay.set_data(data)
            self.lane_overlay.show_at_timestamp(self._current_timestamp_ns())
            self._refresh_lane_view_panes()
            loaded = ", ".join(
                f"{series.role}={len(series.frames)}"
                for series in data.ordered_series()
            )
            self._log(f"Lane line overlay loaded: {loaded} frame(s)")

        def handle_error(message: str) -> None:
            if generation != self._lane_load_generation:
                return
            self.lane_overlay.set_error(f"Lane line overlay failed: {message}")
            self._log(f"Lane line overlay failed: {message}")

        self._run_background(
            title="Loading lane line overlay",
            label="Loading lane line PointCloud2 frames...",
            work=work,
            on_success=handle_success,
            on_error=handle_error,
            parent=self.window,
        )

    def _on_lane_overlay_selection_changed(self) -> None:
        self.lane_overlay.show_at_timestamp(self._current_timestamp_ns())
        self._refresh_lane_view_panes()

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

    def _on_topic_item_changed(self, item: Any, _column: int) -> None:
        topic = item.data(0, self.QtCore.Qt.ItemDataRole.UserRole)
        if not topic:
            return
        info = self._topic_info_by_name.get(str(topic))
        if info is None or lane_role_for_topic(info) is None:
            return
        self._refresh_lane_view_panes()

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

    def _set_theme(self, theme: str) -> None:
        normalized = _normalize_theme(theme)
        if normalized == self._theme:
            self._sync_theme_actions()
            return
        self._theme = normalized
        self._update_settings.setValue("ui/theme", normalized)
        self._sync_theme_actions()
        self._apply_theme()

    def _sync_theme_actions(self) -> None:
        for theme, action in self._theme_actions.items():
            action.blockSignals(True)
            action.setChecked(theme == self._theme)
            action.blockSignals(False)

    def _apply_theme(self) -> None:
        palette = _theme_palette(self._theme)
        stylesheet = _theme_stylesheet(palette)
        app = self.QtWidgets.QApplication.instance()
        if app is not None:
            try:
                app.setStyle("Fusion")
            except Exception:
                pass
            qt_palette = self.QtGui.QPalette()
            roles = [
                self.QtGui.QPalette.ColorGroup.Active,
                self.QtGui.QPalette.ColorGroup.Inactive,
            ]
            for group in roles:
                qt_palette.setColor(group, self.QtGui.QPalette.ColorRole.Window, self.QtGui.QColor(palette["window"]))
                qt_palette.setColor(group, self.QtGui.QPalette.ColorRole.WindowText, self.QtGui.QColor(palette["text"]))
                qt_palette.setColor(group, self.QtGui.QPalette.ColorRole.Base, self.QtGui.QColor(palette["input"]))
                qt_palette.setColor(group, self.QtGui.QPalette.ColorRole.AlternateBase, self.QtGui.QColor(palette["panel"]))
                qt_palette.setColor(group, self.QtGui.QPalette.ColorRole.Text, self.QtGui.QColor(palette["text"]))
                qt_palette.setColor(group, self.QtGui.QPalette.ColorRole.Button, self.QtGui.QColor(palette["button"]))
                qt_palette.setColor(group, self.QtGui.QPalette.ColorRole.ButtonText, self.QtGui.QColor(palette["text"]))
                qt_palette.setColor(group, self.QtGui.QPalette.ColorRole.Highlight, self.QtGui.QColor(palette["accent"]))
                qt_palette.setColor(group, self.QtGui.QPalette.ColorRole.HighlightedText, self.QtGui.QColor(palette["highlight_text"]))
                qt_palette.setColor(group, self.QtGui.QPalette.ColorRole.ToolTipBase, self.QtGui.QColor(palette["panel_alt"]))
                qt_palette.setColor(group, self.QtGui.QPalette.ColorRole.ToolTipText, self.QtGui.QColor(palette["text"]))
                qt_palette.setColor(group, self.QtGui.QPalette.ColorRole.PlaceholderText, self.QtGui.QColor(palette["muted"]))
            qt_palette.setColor(self.QtGui.QPalette.ColorGroup.Disabled, self.QtGui.QPalette.ColorRole.WindowText, self.QtGui.QColor(palette["muted"]))
            qt_palette.setColor(self.QtGui.QPalette.ColorGroup.Disabled, self.QtGui.QPalette.ColorRole.Text, self.QtGui.QColor(palette["muted"]))
            qt_palette.setColor(self.QtGui.QPalette.ColorGroup.Disabled, self.QtGui.QPalette.ColorRole.ButtonText, self.QtGui.QColor(palette["muted"]))
            app.setPalette(qt_palette)
            app.setStyleSheet(stylesheet)
        self.window.setStyleSheet(stylesheet)
        for pane in self._all_panes():
            pane.apply_theme(palette)
        if hasattr(self, "lane_overlay"):
            self.lane_overlay.apply_theme(palette)
        if hasattr(self, "topic_tree"):
            self._apply_topic_tree_item_styles()

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
        if timestamp_ns is None:
            return
        if self.preview is not None:
            for pane in self._all_panes():
                if pane.isVisible():
                    pane.show_at_timestamp(timestamp_ns)
        self.lane_overlay.show_at_timestamp(timestamp_ns)

    def _maybe_offer_startup_update_check(self) -> None:
        mode = str(self._update_settings.value("updates/mode", "") or "")
        if mode not in {"check", "auto", "off"}:
            mode = self._ask_update_preference()
            self._update_settings.setValue("updates/mode", mode)
        if mode == "off":
            return

        def handle_result(info: UpdateInfo | None) -> None:
            if info is None or not info.update_available:
                return
            if mode == "auto":
                self._run_upgrade_from_gui(info, automatic=True)
            else:
                self._show_version_dialog(info)

        self._start_update_check(show_no_update=False, on_result=handle_result)

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

        theme_row = self.QtWidgets.QHBoxLayout()
        theme_row.addWidget(self.QtWidgets.QLabel("Appearance"))
        dark_mode = self.QtWidgets.QCheckBox("Dark mode")
        dark_mode.setChecked(self._theme == "dark")
        dark_mode.toggled.connect(lambda checked: self._set_theme("dark" if checked else "light"))
        theme_row.addWidget(dark_mode)
        theme_row.addStretch(1)
        layout.addLayout(theme_row)

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
            check_button.setEnabled(False)

            def finish(info: UpdateInfo | None) -> None:
                apply_info(info)
                check_button.setEnabled(True)

            self._start_update_check(
                show_no_update=True,
                parent=dialog,
                on_result=finish,
            )

        def upgrade_now() -> None:
            if self._latest_update_info is not None:
                self._run_upgrade_from_gui(self._latest_update_info, parent=dialog)

        check_button.clicked.connect(check_now)
        upgrade_button.clicked.connect(upgrade_now)
        buttons.rejected.connect(dialog.reject)
        apply_info(update_info)
        dialog.exec()

    def _start_update_check(
        self,
        *,
        show_no_update: bool,
        parent: Any | None = None,
        on_result: Any | None = None,
    ) -> None:
        def handle_success(info: UpdateInfo) -> None:
            self._latest_update_info = info
            if info.error:
                if show_no_update:
                    self._show_warning(f"Update check failed: {info.error}")
            elif not info.update_available and show_no_update:
                latest = info.latest_ref or info.latest_version or "unknown"
                self.QtWidgets.QMessageBox.information(
                    parent or self.window,
                    "ros2unbag update",
                    f"No newer version found.\nLatest: {latest}\nInstalled: {info.current_version}",
                )
            if on_result is not None:
                on_result(info)

        def handle_error(message: str) -> None:
            if show_no_update:
                self._show_warning(f"Update check failed: {message}")
            if on_result is not None:
                on_result(None)

        self._run_background(
            title="Checking for updates",
            label="Checking for ros2unbag updates...",
            work=check_for_update,
            on_success=handle_success,
            on_error=handle_error,
            parent=parent,
        )

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
        def work() -> None:
            run_upgrade(build_upgrade_plan(ref=info.latest_ref))

        def finish(_result: object) -> None:
            self.QtWidgets.QMessageBox.information(
                parent or self.window,
                "Upgrade complete",
                "Upgrade finished. Restart ros2unbag to use the updated code.",
            )

        self._run_background(
            title="Upgrade ros2unbag",
            label=f"Upgrading ros2unbag to {info.latest_ref}...",
            work=work,
            on_success=finish,
            on_error=lambda message: self._show_warning(f"Upgrade failed: {message}"),
            parent=parent,
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

    def _run_background(
        self,
        *,
        title: str,
        label: str,
        work: Any,
        on_success: Any,
        on_error: Any | None = None,
        parent: Any | None = None,
    ) -> None:
        progress = self.QtWidgets.QProgressDialog(
            label,
            None,
            0,
            0,
            parent or self.window,
        )
        progress.setWindowTitle(title)
        progress.setWindowModality(self.QtCore.Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)

        results: Queue[tuple[bool, object]] = Queue(maxsize=1)

        def target() -> None:
            try:
                results.put((True, work()))
            except Exception as exc:
                results.put((False, str(exc)))

        thread = Thread(target=target, daemon=True)
        timer = self.QtCore.QTimer(parent or self.window)
        timer.setInterval(50)
        job = (thread, timer, progress, results)
        self._background_jobs.append(job)

        def cleanup() -> None:
            timer.stop()
            progress.close()
            if job in self._background_jobs:
                self._background_jobs.remove(job)

        def poll() -> None:
            try:
                ok, payload = results.get_nowait()
            except Empty:
                return
            cleanup()
            if ok:
                on_success(payload)
            elif on_error is not None:
                on_error(str(payload))
            else:
                self._show_warning(str(payload))

        timer.timeout.connect(poll)
        progress.show()
        timer.start()
        thread.start()


def run_gui(bag_path: str | Path | None = None) -> None:
    _QtCore, _QtGui, QtWidgets = _require_pyside6()
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    viewer = TimelineViewer(bag_path)
    viewer.show()
    app.exec()


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
            self._lane_plot_data: LaneOverlayData | None = None
            self._lane_plot_roles: tuple[str, ...] = ()
            self.setAcceptDrops(True)
            self.setObjectName("topicViewPane")
            self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)

            layout = QtWidgets.QVBoxLayout(self)
            layout.setContentsMargins(6, 6, 6, 6)
            layout.setSpacing(2)
            top_bar = QtWidgets.QHBoxLayout()
            top_bar.setContentsMargins(0, 0, 0, 0)
            self.title_label = QtWidgets.QLabel("Drop topic here")
            self.title_label.setObjectName("viewTitle")
            self.render_button = QtWidgets.QToolButton()
            self.render_button.setText("Render")
            self.xy_button = QtWidgets.QToolButton()
            self.xy_button.setText("XY")
            self.xy_button.setCheckable(True)
            self.xy_button.setEnabled(False)
            self.xy_button.setToolTip("Swap x/y axes for lane line plots")
            self.max_button = QtWidgets.QToolButton()
            self.max_button.setText("Max")
            self.pop_button = QtWidgets.QToolButton()
            self.pop_button.setText("Pop")
            self.delete_button = QtWidgets.QToolButton()
            self.delete_button.setText("X")
            top_bar.addWidget(self.title_label, 1)
            top_bar.addWidget(self.render_button)
            top_bar.addWidget(self.xy_button)
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
            self.lane_plot = owner.LaneOverlayPanel.PlotWidget(self)
            self.lane_plot.set_empty_text("Drop a lane line PointCloud2 topic here.")
            self.raw_text = QtWidgets.QTextEdit()
            self.raw_text.setReadOnly(True)
            self.stack.addWidget(self.image_label)
            self.stack.addWidget(self.point_widget)
            self.stack.addWidget(self.lane_plot)
            self.stack.addWidget(self.raw_text)
            layout.addWidget(self.stack, 1)

            self.render_button.clicked.connect(lambda: self.ensure_rendered_for_playback())
            self.xy_button.toggled.connect(self._on_xy_toggled)
            self.max_button.clicked.connect(lambda: self.owner.toggle_maximize_pane(self))
            self.pop_button.clicked.connect(lambda: self.owner.popout_pane(self))
            self.delete_button.clicked.connect(lambda: self.owner.delete_pane(self))

        def set_view_title(self, title: str) -> None:
            self.view_title = title
            self._refresh_title()

        def apply_theme(self, palette: dict[str, str]) -> None:
            self.image_label.setStyleSheet(
                f"background: {palette['viewer_bg']}; color: {palette['muted']};"
            )
            self.raw_text.setStyleSheet(
                f"background: {palette['input']}; color: {palette['text']};"
            )
            self.lane_plot.apply_theme(palette)

        def clear_topic(self) -> None:
            self.topic = None
            self.topic_info = None
            self.rendered_frames.clear()
            self.rendered_timestamps.clear()
            self.rendered_size = None
            self._lane_plot_data = None
            self._lane_plot_roles = ()
            self._refresh_title()
            self.image_label.clear()
            self.image_label.setText("Drop an image topic or select a topic.")
            self.lane_plot.set_data(None)
            self.lane_plot.set_visible_roles(())
            self.xy_button.setEnabled(False)
            self.set_lane_swap_xy(False)
            self.raw_text.clear()

        def set_topic(self, topic: str, topic_info: TopicInfo) -> None:
            self.topic = topic
            self.topic_info = topic_info
            self.rendered_frames.clear()
            self.rendered_timestamps.clear()
            self.rendered_size = None
            self._lane_plot_data = None
            self._lane_plot_roles = ()
            self._refresh_title()
            self.title_label.setToolTip(topic)
            self.raw_text.setPlainText(f"{topic}\n{topic_info.msgtype}\n{topic_info.category}")
            is_lane = self.is_lane_topic()
            self.xy_button.setEnabled(is_lane)
            self.set_lane_swap_xy(self.owner._lane_swap_xy if is_lane else False)

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

        def is_lane_topic(self) -> bool:
            if self.topic_info is None:
                return False
            return lane_role_for_topic(self.topic_info) is not None

        def set_lane_swap_xy(self, swapped: bool) -> None:
            effective = swapped if self.is_lane_topic() else False
            self.xy_button.blockSignals(True)
            self.xy_button.setChecked(effective)
            self.xy_button.blockSignals(False)
            self.lane_plot.set_swap_xy(effective)

        def _on_xy_toggled(self, checked: bool) -> None:
            self.owner._set_lane_swap_xy(checked)

        def ensure_rendered_for_playback(self) -> bool:
            if self.topic is None or self.topic_info is None:
                self.owner._log("Assign an image topic to this view before rendering.")
                return False
            if self.is_lane_topic():
                self._show_lane_plot_at_timestamp(self.owner._current_timestamp_ns())
                if self.owner._lane_overlay_data is None:
                    self.owner._log("Lane line frames are still loading; the plot will update when ready.")
                return True
            if not self.is_image_topic():
                self.owner._show_warning(
                    "Only image-compatible topics and lane line PointCloud2 topics can be rendered for playback."
                )
                return False
            return self._render_playback_window(self.owner._current_timestamp_ns())

        def _render_playback_window(self, start_timestamp_ns: int | None = None) -> bool:
            if self.topic is None or self.topic_info is None:
                return False
            current_size = _usable_label_size(self.image_label)
            if (
                self.rendered_frames
                and self.rendered_size == current_size
                and start_timestamp_ns is not None
                and self.rendered_timestamps[0] <= start_timestamp_ns <= self.rendered_timestamps[-1]
            ):
                return True
            if self.rendered_frames and self.rendered_size == current_size and start_timestamp_ns is None:
                return True

            reader = self.owner.session.reader
            if reader is None:
                return False
            self.rendered_frames.clear()
            self.rendered_timestamps.clear()
            self.rendered_size = current_size
            total = min(
                self.topic_info.message_count,
                MAX_RENDERED_PLAYBACK_FRAMES,
            ) if self.topic_info.message_count > 0 else MAX_RENDERED_PLAYBACK_FRAMES
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
            skipped_before_window = 0
            for record in reader.iter_messages(topics=[self.topic]):
                if start_timestamp_ns is not None and record.timestamp_ns < start_timestamp_ns:
                    skipped_before_window += 1
                    continue
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
                if count >= MAX_RENDERED_PLAYBACK_FRAMES:
                    break
            progress.setValue(count if total > 0 else 0)
            if not self.rendered_frames:
                self.owner._finish_progress("Ready")
                self.owner._show_warning(f"No frames could be rendered for {self.topic}.")
                return False
            if self.topic_info.message_count > len(self.rendered_frames) + skipped_before_window:
                self.owner._log(
                    f"Rendered {len(self.rendered_frames)} frame(s) for {self.topic} "
                    f"starting near {self.rendered_timestamps[0]}; playback cache is bounded."
                )
            else:
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
            if self.is_lane_topic():
                self._show_lane_plot_at_timestamp(timestamp_ns)
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
            if (
                self.rendered_timestamps
                and len(self.rendered_frames) >= MAX_RENDERED_PLAYBACK_FRAMES
                and (
                    timestamp_ns < self.rendered_timestamps[0]
                    or timestamp_ns > self.rendered_timestamps[-1]
                )
            ):
                if not self._render_playback_window(timestamp_ns):
                    return
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

        def _show_lane_plot_at_timestamp(self, timestamp_ns: int | None) -> None:
            data = self.owner._lane_overlay_data
            roles = tuple(self.owner._lane_roles_for_view(self.topic_info))
            if data is None:
                self.lane_plot.set_empty_text("Loading lane line PointCloud2 frames...")
                if self._lane_plot_data is not None:
                    self.lane_plot.set_data(None)
                    self._lane_plot_data = None
                if self._lane_plot_roles != roles:
                    self.lane_plot.set_visible_roles(roles)
                    self._lane_plot_roles = roles
                self.lane_plot.show_at_timestamp(timestamp_ns)
                self.stack.setCurrentWidget(self.lane_plot)
                return
            self.lane_plot.set_empty_text("No lane line frames were loaded.")
            if self._lane_plot_data is not data:
                self.lane_plot.set_data(data)
                self._lane_plot_data = data
                self._lane_plot_roles = ()
            if self._lane_plot_roles != roles:
                self.lane_plot.set_visible_roles(roles)
                self._lane_plot_roles = roles
            self.lane_plot.show_at_timestamp(timestamp_ns)
            self.stack.setCurrentWidget(self.lane_plot)

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


