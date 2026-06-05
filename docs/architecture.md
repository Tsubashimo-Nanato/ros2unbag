# Architecture

`ros2unbag` is organized as a Python package with a thin command interface over reusable core services.

## Layers

- `ros2unbag.core`: bag readers, topic classification, export policy, manifest generation, timestamp indexing, progress abstractions, preview helpers, update checks, and domain models.
- `ros2unbag.exporters`: format-specific output adapters for CSV, JSONL, raw bytes, images, video, Parquet, SQLite, NPZ, PCD, and PLY.
- `ros2unbag.cli`: Typer commands, REPL parsing/completion, terminal rendering, progress rendering, and upgrade command wiring.
- `ros2unbag.gui`: optional PySide6 timeline viewer shell and render helpers.
- `tests`: unit, integration-style, smoke, GUI behavior, export compatibility, and performance characterization tests.

## Dependency Direction

The intended dependency direction is:

1. CLI and GUI call `Session` and core services.
2. `Session` coordinates readers, manifests, export policy, and exporters.
3. Exporters depend on core models, sanitization, decoding, and point-cloud helpers.
4. Core logic should not depend on CLI or GUI rendering.

The current refactor extracted `ros2unbag.core.export_policy` so format validation, compatibility, defaults, and suggestions can be tested without importing the full session/exporter orchestration.

## Data Flow

1. `open_bag_reader` selects the `rosbags` backend or SQLite fallback.
2. `Session.open_bag` loads topics and classifies them.
3. `Session.scan` builds a manifest and timestamp metadata when needed.
4. `Session.prepare_export_selection` resolves topics and validates export compatibility.
5. `Session._run_export_with_progress` dispatches to a format-specific exporter.
6. Exporters stream or batch messages into Windows-readable output files.

## Testing Strategy

- Keep pure core helpers covered with fast unit tests.
- Keep export compatibility and dispatch tests near `Session`.
- Keep exporter tests focused on output files and metadata sidecars.
- Keep GUI tests limited to behavior that can run without opening real ROS bags.
- Use per-tag pytest runs as archaeology characterization data.

## Known Limitations

- GUI code is still the largest and most coupled interface layer.
- `Session` remains the central orchestration object and still owns many workflows.
- Exporters contain format-specific streaming optimizations that should remain local to each exporter.
- No CI workflow was present during inventory.
