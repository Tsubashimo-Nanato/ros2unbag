# Changelog

All notable changes for this project will be documented in this file.

## [1.2.2] - 2026-05-11

Bugfix and export robustness release.

### Fixed

- Rejected unknown bag reader backends before opening a session and preserved the previous session state when open failed.
- Preserved empty arrays and dictionaries when flattening decoded messages.
- Respected `PointCloud2` row padding and avoided reading fields across point boundaries.
- Suggested tabular export formats for point cloud topics.
- Preserved distinct SQLite topic table names for topic paths that differ only by punctuation.
- Inferred numeric SQLite column types from exported row values.
- Deduplicated raw export warnings.

## [1.2.0] - 2026-05-06

Phase 4 tabular export release.

### Added

- Parquet export for flattened tabular topic data.
- SQLite session export with metadata tables, message rows, export records, and per-topic flattened tables.
- Shared tabular export collection for CSV, Parquet, and SQLite outputs, including PointCloud2 point-row expansion and raw metadata fallback rows.
- CLI and interactive shell support for dispatching `parquet` and `sqlite` export formats.

## [1.0.0] - 2026-04-28

Initial public release preparation.

### Added

- Offline ROS bag scanning with topic metadata, message counts, timestamp ranges, and category hints.
- Interactive `ros2unbag` shell with command history and topic/path completion.
- CLI commands for `scan`, `topics`, `export`, `export-all`, `inspect`, `dur`, `manifest`, `formats`, and `uninstall`.
- CSV export for scalar/simple decoded messages and point-row export for decoded `sensor_msgs/msg/PointCloud2`.
- JSONL export for arbitrary decoded messages.
- PNG/JPG image sequence export for supported decoded image topics, with timestamp CSV sidecars.
- MP4 export for decoded image topics at constant FPS, with timestamp CSV sidecars preserving true ROS timestamps.
- Raw serialized export for undecoded or unsupported topics.
- Installation via `pip install -e .`.

### Known Incomplete Areas

- At the time of the 1.0.0 release, Parquet and SQLite exports were recognized as planned formats but were not implemented yet.
- The PySide6 GUI timeline viewer is reserved for future work and is not implemented.
- Image decoding is limited to common 8-bit encodings and OpenCV-decodable compressed images.
- Custom message support depends on what `rosbags` can deserialize from bag metadata unless future custom definition loading is added.
