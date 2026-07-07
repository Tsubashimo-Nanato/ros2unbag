from __future__ import annotations

from typing import Any, Callable

from ros2unbag.core.lane_lines import (
    LANE_ROLES,
    LaneBounds,
    LaneFrame,
    LaneOverlayData,
    LanePoint,
    LaneSeries,
)


LANE_COLORS = {
    "center": "#f2c94c",
    "left": "#2f80ed",
    "right": "#eb5757",
}


def create_lane_overlay_panel_class(
    QtWidgets: Any,
    QtCore: Any,
    QtGui: Any,
) -> type:
    class LanePlotWidget(QtWidgets.QWidget):
        def __init__(self, parent: Any | None = None) -> None:
            super().__init__(parent)
            self._palette = {
                "viewer_bg": "#edf0f3",
                "panel": "#ffffff",
                "text": "#202124",
                "muted": "#636a73",
                "border": "#c7ccd4",
            }
            self._data: LaneOverlayData | None = None
            self._visible_roles: set[str] = set()
            self._timestamp_ns: int | None = None
            self._bounds: LaneBounds | None = None
            self.setMinimumSize(300, 260)

        @property
        def current_timestamp_ns(self) -> int | None:
            return self._timestamp_ns

        def apply_theme(self, palette: dict[str, str]) -> None:
            self._palette = dict(palette)
            self.update()

        def set_data(self, data: LaneOverlayData | None) -> None:
            self._data = data
            self._refresh_bounds()
            self.update()

        def set_visible_roles(self, roles: list[str] | tuple[str, ...] | set[str]) -> None:
            self._visible_roles = set(roles)
            self._refresh_bounds()
            self.update()

        def show_at_timestamp(self, timestamp_ns: int | None) -> None:
            self._timestamp_ns = timestamp_ns
            self.update()

        def paintEvent(self, _event: Any) -> None:
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
            rect = self.rect()
            palette = self._palette
            painter.fillRect(rect, QtGui.QColor(palette["viewer_bg"]))

            plot_rect = self._plot_rect(rect)
            self._draw_grid(painter, plot_rect)

            if self._data is None:
                self._draw_center_text(painter, plot_rect, "Open a bag with lane line PointCloud2 topics.")
                painter.end()
                return
            if not self._visible_roles:
                self._draw_center_text(painter, plot_rect, "Select a lane line topic.")
                painter.end()
                return
            if self._bounds is None:
                self._draw_center_text(painter, plot_rect, "Selected lane topics have no x/y points.")
                painter.end()
                return

            frame_items = self._current_frames()
            if not frame_items:
                self._draw_center_text(painter, plot_rect, "No frame is available at this time.")
                painter.end()
                return

            mapper = self._point_mapper(plot_rect, self._bounds)
            for series, frame in frame_items:
                self._draw_frame(painter, mapper, series, frame)
            self._draw_legend(painter, plot_rect, frame_items)
            self._draw_axes(painter, plot_rect)
            painter.end()

        def _refresh_bounds(self) -> None:
            if self._data is None:
                self._bounds = None
                return
            self._bounds = self._data.bounds_for_roles(self._visible_roles)

        def _current_frames(self) -> list[tuple[LaneSeries, LaneFrame]]:
            if self._data is None or self._timestamp_ns is None:
                return []
            frames: list[tuple[LaneSeries, LaneFrame]] = []
            for series in self._data.ordered_series(LANE_ROLES):
                if series.role not in self._visible_roles:
                    continue
                frame = series.nearest_frame(self._timestamp_ns)
                if frame is not None:
                    frames.append((series, frame))
            return frames

        def _plot_rect(self, rect: Any) -> Any:
            left = 46.0
            top = 22.0
            right = 18.0
            bottom = 36.0
            width = max(1.0, float(rect.width()) - left - right)
            height = max(1.0, float(rect.height()) - top - bottom)
            return QtCore.QRectF(left, top, width, height)

        def _draw_grid(self, painter: Any, plot_rect: Any) -> None:
            border = QtGui.QColor(self._palette["border"])
            muted = QtGui.QColor(self._palette["muted"])
            muted.setAlpha(55)
            painter.setPen(QtGui.QPen(muted, 1))
            for index in range(1, 5):
                x = plot_rect.left() + (plot_rect.width() * index / 5.0)
                y = plot_rect.top() + (plot_rect.height() * index / 5.0)
                painter.drawLine(
                    QtCore.QPointF(x, plot_rect.top()),
                    QtCore.QPointF(x, plot_rect.bottom()),
                )
                painter.drawLine(
                    QtCore.QPointF(plot_rect.left(), y),
                    QtCore.QPointF(plot_rect.right(), y),
                )
            painter.setPen(QtGui.QPen(border, 1))
            painter.drawRect(plot_rect)

        def _draw_axes(self, painter: Any, plot_rect: Any) -> None:
            painter.setPen(QtGui.QColor(self._palette["muted"]))
            painter.drawText(
                QtCore.QRectF(plot_rect.left(), plot_rect.bottom() + 8, plot_rect.width(), 20),
                QtCore.Qt.AlignmentFlag.AlignCenter,
                "x",
            )
            painter.drawText(
                QtCore.QRectF(6, plot_rect.top(), 32, plot_rect.height()),
                QtCore.Qt.AlignmentFlag.AlignCenter,
                "y",
            )

        def _draw_center_text(self, painter: Any, plot_rect: Any, text: str) -> None:
            painter.setPen(QtGui.QColor(self._palette["muted"]))
            painter.drawText(
                plot_rect,
                QtCore.Qt.AlignmentFlag.AlignCenter | QtCore.Qt.TextFlag.TextWordWrap,
                text,
            )

        def _point_mapper(
            self,
            plot_rect: Any,
            bounds: LaneBounds,
        ) -> Callable[[LanePoint], Any]:
            data_width = max(1e-9, bounds.max_x - bounds.min_x)
            data_height = max(1e-9, bounds.max_y - bounds.min_y)
            scale = min(plot_rect.width() / data_width, plot_rect.height() / data_height)
            drawn_width = data_width * scale
            drawn_height = data_height * scale
            x_pad = (plot_rect.width() - drawn_width) / 2.0
            y_pad = (plot_rect.height() - drawn_height) / 2.0

            def map_point(point: LanePoint) -> Any:
                x = plot_rect.left() + x_pad + ((point.x - bounds.min_x) * scale)
                y = plot_rect.top() + y_pad + ((bounds.max_y - point.y) * scale)
                return QtCore.QPointF(x, y)

            return map_point

        def _draw_frame(
            self,
            painter: Any,
            map_point: Callable[[LanePoint], Any],
            series: LaneSeries,
            frame: LaneFrame,
        ) -> None:
            if not frame.points:
                return
            color = QtGui.QColor(LANE_COLORS[series.role])
            painter.setPen(QtGui.QPen(color, 2))
            if len(frame.points) > 1:
                path = QtGui.QPainterPath(map_point(frame.points[0]))
                for point in frame.points[1:]:
                    path.lineTo(map_point(point))
                painter.drawPath(path)
            painter.setBrush(color)
            painter.setPen(QtGui.QPen(color, 1))
            for point in frame.points:
                painter.drawEllipse(map_point(point), 2.8, 2.8)

        def _draw_legend(
            self,
            painter: Any,
            plot_rect: Any,
            frame_items: list[tuple[LaneSeries, LaneFrame]],
        ) -> None:
            top = plot_rect.top() + 8.0
            left = plot_rect.left() + 8.0
            painter.setPen(QtGui.QColor(self._palette["text"]))
            if self._timestamp_ns is not None:
                painter.drawText(
                    QtCore.QRectF(left, top, plot_rect.width() - 16, 18),
                    QtCore.Qt.AlignmentFlag.AlignRight,
                    f"{self._timestamp_ns} ns",
                )
            for index, (series, frame) in enumerate(frame_items):
                y = top + 2.0 + (index * 20.0)
                color = QtGui.QColor(LANE_COLORS[series.role])
                painter.setBrush(color)
                painter.setPen(QtGui.QPen(color, 1))
                painter.drawEllipse(QtCore.QPointF(left + 5.0, y + 7.0), 4.0, 4.0)
                painter.setPen(QtGui.QColor(self._palette["text"]))
                painter.drawText(
                    QtCore.QRectF(left + 16.0, y, 180.0, 18.0),
                    QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter,
                    f"{series.role}: {len(frame.points)} pts",
                )

    class LaneOverlayPanel(QtWidgets.QWidget):
        def __init__(
            self,
            parent: Any | None = None,
            on_selection_changed: Callable[[], None] | None = None,
        ) -> None:
            super().__init__(parent)
            self._on_selection_changed = on_selection_changed
            self._topics_by_role: dict[str, Any] = {}
            self._data: LaneOverlayData | None = None

            layout = QtWidgets.QVBoxLayout(self)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(8)

            check_row = QtWidgets.QHBoxLayout()
            check_row.setContentsMargins(0, 0, 0, 0)
            self.checkboxes: dict[str, Any] = {}
            for role in LANE_ROLES:
                checkbox = QtWidgets.QCheckBox(role)
                checkbox.setObjectName(f"lane_{role}_check")
                checkbox.setEnabled(False)
                checkbox.setToolTip(f"Show {role} lane line points")
                checkbox.toggled.connect(self._selection_changed)
                self.checkboxes[role] = checkbox
                check_row.addWidget(checkbox)
            check_row.addStretch(1)
            layout.addLayout(check_row)

            self.status_label = QtWidgets.QLabel("Open a bag with lane line PointCloud2 topics.")
            self.status_label.setWordWrap(True)
            layout.addWidget(self.status_label)

            self.plot = LanePlotWidget(self)
            layout.addWidget(self.plot, 1)

        @property
        def current_timestamp_ns(self) -> int | None:
            return self.plot.current_timestamp_ns

        def apply_theme(self, palette: dict[str, str]) -> None:
            self.status_label.setStyleSheet(f"color: {palette['muted']};")
            self.plot.apply_theme(palette)

        def set_topics(self, topics_by_role: dict[str, Any]) -> None:
            self._topics_by_role = dict(topics_by_role)
            self._data = None
            for role, checkbox in self.checkboxes.items():
                checkbox.blockSignals(True)
                checkbox.setEnabled(role in self._topics_by_role)
                checkbox.setChecked(role in self._topics_by_role)
                checkbox.blockSignals(False)
            self.plot.set_data(None)
            self.plot.set_visible_roles(self.visible_roles())
            if self._topics_by_role:
                roles = ", ".join(self._topics_by_role)
                self.status_label.setText(f"Detected lane topics: {roles}.")
            else:
                self.status_label.setText("No lane line topics found in this bag.")

        def set_loading(self) -> None:
            self.status_label.setText("Loading lane line frames...")

        def set_error(self, message: str) -> None:
            self.status_label.setText(message)

        def set_data(self, data: LaneOverlayData) -> None:
            self._data = data
            self.plot.set_data(data)
            self.plot.set_visible_roles(self.visible_roles())
            if not data.series_by_role:
                self.status_label.setText("No lane line frames were loaded.")
                return
            pieces = [
                f"{series.role}: {len(series.frames)} frames"
                for series in data.ordered_series(LANE_ROLES)
            ]
            self.status_label.setText("; ".join(pieces))

        def show_at_timestamp(self, timestamp_ns: int | None) -> None:
            self.plot.show_at_timestamp(timestamp_ns)

        def visible_roles(self) -> list[str]:
            return [
                role
                for role in LANE_ROLES
                if self.checkboxes[role].isEnabled() and self.checkboxes[role].isChecked()
            ]

        def _selection_changed(self, _checked: bool) -> None:
            self.plot.set_visible_roles(self.visible_roles())
            if self._on_selection_changed is not None:
                self._on_selection_changed()

    return LaneOverlayPanel
