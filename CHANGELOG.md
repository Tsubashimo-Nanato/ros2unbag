# Changelog

All notable changes for this project will be documented in this file.

## [1.4.3] - 2026-05-18

Shell upgrade and Windows progress fallback release.

### Added

- Added `ros2unbag upgrade` and interactive `upgrade` shell support for upgrading the installed package from GitHub or PyPI.
- Added `--ref` support for upgrading from a specific GitHub branch, tag, commit, or exact PyPI version.

### Fixed

- Switched Windows consoles to a bounded single-line progress fallback to avoid repeated-line output flooding in `cmd.exe`.

## [1.4.2] - 2026-05-14

Stress-test and progress performance release.

### Changed

- Replaced the default progress bar with a fixed-width block bar.
- Batched progress updates for large scans and exports to reduce terminal rendering overhead.
- Optimized `inspect --time` to use a streaming nearest-message query when bag time bounds are available, avoiding a full in-memory timestamp index for common bags.

### Tested

- Added synthetic stress coverage for progress rendering and streaming inspect behavior.
- Stress-tested scan, timestamp indexing, and streaming inspect on a synthetic 250,000-message, 80-topic reader.

## [1.4.1] - 2026-05-14

Shell and topic display cleanup release.

### Changed

- Simplified topic tree colors and removed repeated full path text from tree rows.
- Highlighted topic names in orange in scan table and topic tree output.
- Moved browsing variants to `topics`, with `topics`, `topics -all`, and `topics -s`.
- Simplified `scan` to the full scan workflow and removed the scan backend/view options.
- Updated REPL completion so `scan` suggests `--all` after a bag is open and `topics` suggests `-all` and `-s`.

## [1.4.0] - 2026-05-14

Selected export and shell UX release.

### Added

- Added interactive `export-select` mode for queueing multiple topic exports, reviewing a confirmation table, and exporting the selected set.
- Added `inspect --dur TOPIC` so nearest-message inspection and topic duration checks can be run from one inspect command.

### Changed

- REPL Ctrl+C handling now interrupts the current action without closing the shell.
- REPL completion now covers `export-select`, `inspect --dur`, and the `topics -v` shortcut more directly.
- Topic tree and opened-bag status rendering now use clearer color-coded paths.
- Progress bars now include ETA when the backend provides a message count and print an interruption summary when cancelled.

## [1.3.4] - 2026-05-14

Export compatibility release.

### Changed

- Topic exports now reject incompatible media formats early, such as exporting point clouds or custom structs as `mp4`, `png`, or `jpg`.
- Flexible data exports remain available across topic types, including image topics exported as `csv`, `jsonl`, `parquet`, `sqlite`, or `raw`.
- Topic export suggestions now show tabular/raw flexibility for image topics and JSONL flexibility for point clouds.

## [1.3.2] - 2026-05-14

Interactive shell completion release.

### Changed

- REPL tab completion now advances through the next expected arguments and options for common commands, such as `export TOPIC --format FORMAT --out OUT_DIR`.
- REPL option completion now avoids suggesting options that are already present by either their short or long form.

## [1.3.1] - 2026-05-12

Performance release.

### Changed

- Single-topic exports now use backend metadata for bag start/end timestamps when available instead of building a full-bag timestamp index before export.
- Bag time bounds are cached per session after they are discovered.

## [1.3.0] - 2026-05-12

Progress and package naming release.

### Added

- Rich progress display for bag opening and progress bars for scan/indexing, exports, image sequence output, and MP4 video output.
- Shared progress callback plumbing for manifest scans, timestamp indexing, and all implemented exporters.

### Changed

- Renamed the Python import package from `ros2_unbag` to `ros2unbag` so the distribution, command, and import name match.
- Removed the unused `tqdm` runtime dependency; progress rendering now uses the existing Rich dependency.

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
