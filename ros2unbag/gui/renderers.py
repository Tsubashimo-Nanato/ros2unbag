from __future__ import annotations

from typing import Any, Protocol


class PointCloudRenderer(Protocol):
    def widget(self) -> Any:
        raise NotImplementedError

    def set_points(self, points: Any, color_values: Any | None = None) -> None:
        raise NotImplementedError


class NullPointCloudRenderer:
    """Fallback renderer used when VisPy/OpenGL is unavailable."""

    def __init__(self, QtWidgets: Any) -> None:
        self._label = QtWidgets.QLabel("Point cloud renderer unavailable")

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

    def widget(self) -> Any:
        return self._canvas

    def set_points(self, points: Any, color_values: Any | None = None) -> None:
        colors = None
        if color_values is not None and len(color_values):
            values = self._np.asarray(color_values, dtype=self._np.float32)
            span = float(values.max() - values.min()) or 1.0
            normalized = (values - values.min()) / span
            colors = self._np.column_stack(
                [normalized, 1.0 - normalized, self._np.full_like(normalized, 0.25), self._np.ones_like(normalized)]
            )
        self._scatter.set_data(
            self._np.asarray(points, dtype=self._np.float32),
            face_color=colors if colors is not None else (1.0, 0.62, 0.11, 0.85),
            size=3,
        )
        self._canvas.update()


def create_point_cloud_renderer(QtWidgets: Any) -> PointCloudRenderer:
    try:
        return VisPyPointCloudRenderer()
    except Exception:
        return NullPointCloudRenderer(QtWidgets)
