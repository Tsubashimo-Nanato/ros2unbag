# Changelog

All notable changes for this project will be documented in this file.

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

- Parquet and SQLite exports are recognized as planned formats but are not implemented yet.
- The PySide6 GUI timeline viewer is reserved for future work and is not implemented.
- Image decoding is limited to common 8-bit encodings and OpenCV-decodable compressed images.
- Custom message support depends on what `rosbags` can deserialize from bag metadata unless future custom definition loading is added.
