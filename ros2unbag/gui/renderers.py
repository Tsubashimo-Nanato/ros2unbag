from __future__ import annotations

from typing import Any, Protocol


POINT_CLOUD_HELP_TEXT = (
    "Drag: rotate or pan\n"
    "Wheel: zoom\n"
    "The view fits new point frames automatically."
)
POINT_CLOUD_FIT_MARGIN_RATIO = 0.04


class PointCloudRenderer(Protocol):
    def widget(self) -> Any:
        raise NotImplementedError

    def set_points(self, points: Any, color_values: Any | None = None) -> None:
        raise NotImplementedError


class NullPointCloudRenderer:
    """Fallback renderer used when VisPy/OpenGL is unavailable."""

    def __init__(self, QtWidgets: Any) -> None:
        self._label = QtWidgets.QLabel("Point cloud renderer unavailable")
        self._label.setToolTip(POINT_CLOUD_HELP_TEXT)

    def widget(self) -> Any:
        return self._label

    def set_points(self, points: Any, color_values: Any | None = None) -> None:
        count = len(points) if hasattr(points, "__len__") else 0
        self._label.setText(f"{count} point preview loaded; VisPy renderer unavailable.")


class VisPyPointCloudRenderer:
    """Optional VisPy point cloud renderer embedded in a Qt widget."""

    def __init__(self) -> None:
        import numpy as np
        from vispy import scene
        from vispy.app.qt import QtSceneCanvas

        self._np = np
        self._canvas = QtSceneCanvas(keys=None, bgcolor="#101010")
        self._view = self._canvas.central_widget.add_view()
        self._view.camera = "turntable"
        scene.visuals.XYZAxis(parent=self._view.scene)
        self._scatter = scene.visuals.Markers(parent=self._view.scene)
        self._canvas.setToolTip(POINT_CLOUD_HELP_TEXT)

    def widget(self) -> Any:
        return self._canvas

    def set_points(self, points: Any, color_values: Any | None = None) -> None:
        points_array = self._np.asarray(points, dtype=self._np.float32)
        if points_array.size == 0:
            points_array = points_array.reshape((0, 3))
        elif points_array.ndim == 1:
            points_array = points_array.reshape((-1, 3))
        colors = None
        if color_values is not None and len(color_values) == len(points_array):
            values = self._np.asarray(color_values, dtype=self._np.float32)
            span = float(values.max() - values.min()) or 1.0
            normalized = (values - values.min()) / span
            colors = self._np.column_stack(
                [normalized, 1.0 - normalized, self._np.full_like(normalized, 0.25), self._np.ones_like(normalized)]
            )
        self._scatter.set_data(
            points_array,
            face_color=colors if colors is not None else (1.0, 0.62, 0.11, 0.85),
            size=3,
        )
        self._fit_camera(points_array)
        self._canvas.update()

    def _fit_camera(self, points: Any) -> None:
        if points.size == 0:
            return
        finite = points[self._np.isfinite(points).all(axis=1)]
        if finite.size == 0:
            return
        mins = finite.min(axis=0)
        maxs = finite.max(axis=0)
        span = maxs - mins
        max_span = max(float(span.max()), 1.0)
        margin = max_span * POINT_CLOUD_FIT_MARGIN_RATIO
        camera = self._view.camera
        camera.set_range(
            x=(float(mins[0] - margin), float(maxs[0] + margin)),
            y=(float(mins[1] - margin), float(maxs[1] + margin)),
            z=(float(mins[2] - margin), float(maxs[2] + margin)),
            margin=0.02,
        )


def create_point_cloud_renderer(QtWidgets: Any) -> PointCloudRenderer:
    try:
        return VisPyPointCloudRenderer()
    except Exception:
        return NullPointCloudRenderer(QtWidgets)
