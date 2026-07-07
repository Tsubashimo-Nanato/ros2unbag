# ros2unbag

Unbag your ROS2 bags in Windows!

`ros2unbag` is a Windows-based Python command-line tool for inspecting ROS bag files offline. It reads bags without having to play them on Linux, lists topics and message types, builds timestamp indexes, classifies topics into practical export categories, and exports selected data into Windows-readable formats.

This tool is oriented toward researchers who prefer working in Windows rather than moving every bag-inspection task into a Linux ROS environment. It is designed for quickly extracting bag data into practical analysis formats such as CSV, Parquet, SQLite, PNG/JPG image sequences, MP4 video, PCD/PLY point cloud sequences, NPZ arrays, JSONL, and raw serialized dumps.

## Status

Current release: `v1.6.0`

Release preparation date: 2026-06-13

This project has been publicly released and is currently maintained at version `1.6.0`. The core workflow is usable in real offline bag-inspection and export workflows, while some features remain incomplete and edge cases may still exist.

Developer and maintainer: Owen Zi-Wen ZHOU. Reviewed and released by Owen Zi-Wen ZHOU. Issues, bug reports, and improvement suggestions are welcome.

## Features

- Offline ROS bag inspection without `ros2 bag play`.
- Preferred `rosbags` backend for reading rosbag1 and rosbag2 data without requiring a full ROS installation.
- SQLite fallback backend for basic ROS 2 `.db3` scans and raw exports when decoded message support is unavailable.
- Topic table, namespace tree, and interactive topic navigation views.
- Timestamp indexing and nearest-message inspection by bag-relative time.
- Topic duration reporting with bag-relative start and end coverage.
- CSV export for scalar/simple decoded messages and decoded `sensor_msgs/msg/PointCloud2` point rows.
- JSONL export for arbitrary decoded messages.
- PNG and JPG image sequence export for supported decoded image topics.
- MP4 export for decoded image topics using constant FPS.
- Parquet export for flattened tabular topic data.
- SQLite session export with topic metadata, message rows, export records, and per-topic flattened tables.
- PCD and PLY sequence export for decoded `sensor_msgs/msg/PointCloud2` topics.
- NPZ export for point clouds, numeric topics, and image/depth frames.
- Timestamp sidecar CSV files for image, video, and raw exports.
- Raw serialized dumps for unsupported or undecoded topics.
- Topic-aware export validation that blocks incompatible media exports while keeping flexible data exports available.
- Interactive REPL shell with command history and context-aware tab completion.
- Interactive selected-export mode for queueing multiple topic exports, reviewing a confirmation table, and exporting the selected set.
- Shell upgrade command for updating an installed copy from GitHub or PyPI.
- Non-flooding progress display for bag opening and block-style progress bars for scan/indexing, exports, image sequence output, and MP4 video output, with ETA when totals are available.
- Metadata-based bag time bounds when available, avoiding a full-bag pre-index scan for single-topic exports.
- Streaming nearest-message inspection when bag time bounds are available, avoiding a full in-memory timestamp index for common `inspect --time` workflows.
- Optional PySide6 timeline viewer shell for offline bag inspection and non-destructive display/export settings.

## Installation

From this repository:

```powershell
py -m pip install -e .
```

The distribution name, installed command, and Python import package are all `ros2unbag`.

On Windows, the Python Scripts directory is sometimes not on `PATH`, so `py -m pip install -e .` may succeed while `ros2unbag` is still not recognized in a new terminal. The repository includes batch helpers for this:

```bat
install.bat
install.bat gui
```

`install.bat` installs the package, adds the current Python Scripts directory to the user `PATH`, and keeps a repo-local fallback launcher:

```bat
ros2unbag.bat
```

Restart the terminal after running `install.bat` before using `ros2unbag` directly.

Optional GUI install:

```powershell
py -m pip install -e .[gui]
```

Upgrade an installed copy from the GitHub repository:

```powershell
ros2unbag upgrade --yes
```

Preview the upgrade command:

```powershell
ros2unbag upgrade --print-only
```

Upgrade from a specific GitHub tag, branch, or commit:

```powershell
ros2unbag upgrade --ref v1.6.0 --yes
```

The running shell process cannot reload upgraded Python code in place. Restart `ros2unbag` after a successful upgrade.

Uninstall:

```powershell
ros2unbag uninstall --yes
```

Windows batch uninstall:

```bat
uninstall.bat
```

The uninstall script does not remove the Python Scripts directory from `PATH` because that directory may be shared by other Python tools.

Preview the exact uninstall command:

```powershell
ros2unbag uninstall --print-only
```

If `ros2unbag` is not on `PATH`, use Python directly:

```powershell
py -m ros2unbag.cli.main uninstall --yes
```

## Interactive Mode

Run `ros2unbag` with no command to start the interactive shell:

```powershell
ros2unbag
```

The prompt is:

```text
ros2unbag>
```

Typical session:

```text
ros2unbag> open .\my_bag
ros2unbag> topics
ros2unbag> topics -all
ros2unbag> scan --all
ros2unbag> dur /aiformula_perception/lane_line_publisher/lane_lines/center
ros2unbag> inspect --time 25.0 --dur /camera/image_raw
ros2unbag> export /aiformula_control/joy --format csv --out .\export
ros2unbag> export /aiformula_control/joy --format parquet --out .\export
ros2unbag> export /aiformula_control/joy --format sqlite --out .\export
ros2unbag> export /camera/image_raw --format mp4 --fps 30 --out .\export
ros2unbag> export-select
ros2unbag> export-all --out .\export
ros2unbag> gui
ros2unbag> upgrade
ros2unbag> close
ros2unbag> exit
```

Interactive commands:

- `open BAG_PATH`
- `scan [BAG_PATH] [--all] [--out OUT_DIR]`
- `topics`
- `topics -all`
- `topics -s`
- `dur TOPIC`
- `export TOPIC --format csv|parquet|sqlite|png|jpg|mp4|jsonl|raw|npz|pcd|ply --out OUT_DIR [--fps FPS]`
- `export-select`
- `export-all --out OUT_DIR`
- `inspect --time SECONDS [--dur TOPIC] [--absolute-ns]`
- `gui [BAG_PATH]`
- `upgrade [--source github|pypi] [--ref REF] [--yes]`
- `close`
- `help`
- `clear`
- `exit` or `quit`

The REPL uses `prompt-toolkit`. Tab completes command names, options such as `--all`, `-all`, `-s`, `--format`, `--out`, `--time`, `--dur`, `--source`, option values, and filesystem paths. After `open BAG_PATH`, Tab also completes topic names from the opened bag. For common workflows, Tab advances through the next expected parameter; for example, after completing an export topic it suggests `--format`, then format values, then `--out`. Press Tab twice to show possible completions. History is stored in `.ros2unbag_history` in the current working directory and is ignored by Git.

Long-running REPL commands render a single live progress display when the terminal supports it. On Windows consoles, including `cmd.exe`, `ros2unbag` uses a bounded single-line fallback progress display to avoid repeated-line output from live terminal rendering. Pressing Ctrl+C interrupts the current action and returns to the shell instead of closing the shell.

Selected export mode:

```text
ros2unbag> export-select
select> /imu --format csv --out .\export
select> /camera/image_raw --format mp4 --fps 30 --out .\export
select> export-all
```

Before the selected exports run, `ros2unbag` displays a confirmation table and asks for `y` or `n`.

## Command-Line Usage

Scan a bag and print the full detailed topic table:

```powershell
ros2unbag scan .\my_bag
```

For a first pass on an unfamiliar bag, start with the topic tree:

```powershell
ros2unbag topics .\my_bag
```

The tree view is usually the fastest way to understand topic namespaces. Use `topics -all` or `scan --all` afterward when you need counts, durations, categories, and export suggestions.

The default scan view is a compact table. The first column is the topic leaf name, such as `cmd_vel`, and the second column is the parent topic path, such as `/aiformula_control/game_pad`.

Topic display modes:

```powershell
ros2unbag topics .\my_bag
ros2unbag topics .\my_bag -all
ros2unbag topics .\my_bag -s
```

Use `topics` to see the namespace tree. Use `topics -all` for the detailed table. Use `topics -s` for an interactive browser where you enter `1`, `2`, `3`, and so on to open a namespace or topic, `b` or `back` to go up, and `q` or `quit` to exit.

Scan and write `manifest.json` and `topics.csv`:

```powershell
ros2unbag scan .\my_bag --out .\exported_scan
```

Export one topic:

```powershell
ros2unbag export .\my_bag --topic /imu --format csv --out .\export
ros2unbag export .\my_bag --topic /imu --format parquet --out .\export
ros2unbag export .\my_bag --topic /imu --format sqlite --out .\export
ros2unbag export .\my_bag --topic /diagnostics --format jsonl --out .\export
ros2unbag export .\my_bag --topic /camera/image_raw --format png --out .\export
ros2unbag export .\my_bag --topic /camera/image_raw --format jpg --out .\export
ros2unbag export .\my_bag --topic /camera/image_raw --format mp4 --fps 30 --out .\export
ros2unbag export .\my_bag --topic /camera/depth --format npz --out .\export
ros2unbag export .\my_bag --topic /points --format pcd --out .\export
ros2unbag export .\my_bag --topic /points --format ply --out .\export
ros2unbag export .\my_bag --topic /points --format npz --out .\export
ros2unbag export .\my_bag --topic /unknown/custom_topic --format raw --out .\export
```

Export all compatible topics using default implemented formats:

```powershell
ros2unbag export-all .\my_bag --out .\export
```

Interactively queue selected topic exports, review the confirmation table, then run the selected set:

```powershell
ros2unbag export-select .\my_bag --out .\export
```

Inspect nearest messages at 145 seconds after bag start:

```powershell
ros2unbag inspect .\my_bag --time 145.0
```

Inspect nearest messages and show duration for one topic in the same command:

```powershell
ros2unbag inspect .\my_bag --time 145.0 --dur /camera/image_raw
```

Show duration and bag-relative coverage for one topic:

```powershell
ros2unbag dur .\my_bag /aiformula_perception/lane_line_publisher/lane_lines/center
```

Write only a manifest:

```powershell
ros2unbag manifest .\my_bag --out .\manifest.json
```

List recognized export formats:

```powershell
ros2unbag formats
```

Start the optional GUI timeline viewer:

```powershell
ros2unbag gui .\my_bag
```

Upgrade the installed package:

```powershell
ros2unbag upgrade --yes
ros2unbag upgrade --ref v1.6.0 --yes
ros2unbag upgrade --source pypi --yes
```

Typer shell completion is available:

```powershell
ros2unbag --install-completion powershell
ros2unbag --show-completion powershell
```

Long-running command-line operations render a single progress display instead of printing per-message status lines. Progress is shown for bag opening, full scans, timestamp indexing used by `inspect` and `dur`, single-topic exports, selected exports, `export-all`, image sequence output, and MP4 video output. When a backend provides message counts, the progress display uses a block-style bar and includes estimated time remaining. On Windows consoles, including `cmd.exe`, `ros2unbag` uses a bounded single-line fallback to avoid Rich live-rendering output floods. If the output is redirected or the terminal does not support progress rendering, progress output is disabled. Set `ROS2UNBAG_PLAIN_PROGRESS=1` to force the fallback progress renderer.

## Example Workflow

```powershell
py -m pip install -e .
ros2unbag topics .\my_bag
ros2unbag scan .\my_bag --out .\scan
ros2unbag dur .\my_bag /camera/image_raw
ros2unbag export .\my_bag --topic /camera/image_raw --format png --out .\export
ros2unbag inspect .\my_bag --time 25.0
```

For image sequence export, the output layout is:

```text
export/images/<sanitized_topic_name>/
  000000.png
  000001.png
  timestamps.csv
```

For MP4 export, the output layout is:

```text
export/videos/<sanitized_topic_name>.mp4
export/videos/<sanitized_topic_name>_timestamps.csv
```

MP4 export currently uses `constant_fps` mode. The video plays frames sequentially at `--fps`, while the timestamp sidecar preserves the true ROS timestamps because bag timestamps are not guaranteed to be uniform.

Timestamp CSV sidecars include the source ROS timestamp in nanoseconds and `timestamp_sec_from_start` relative to the bag start. Image, video, point cloud, and NPZ sidecars also include frame index and output filename plus format-specific metadata.

For point cloud sequence export, the output layout is:

```text
export/pointclouds/<sanitized_topic_name>/
  000000.pcd
  000001.pcd
  timestamps.csv
```

Use `--format ply` for PLY output in the same folder layout. PCD/PLY exports are lossless for supported numeric `PointCloud2` fields and preserve common fields such as `x`, `y`, `z`, `intensity`, `rgb`, `rgba`, `ring`, and `time` when present.

NPZ export writes either one numeric topic file or a per-frame sequence for image and point cloud topics:

```text
export/npz/<sanitized_topic_name>.npz
export/npz/<sanitized_topic_name>/000000.npz
```

Parquet export writes one `.parquet` file per selected topic:

```text
export/parquet/<sanitized_topic_name>.parquet
```

SQLite export writes or updates one session database:

```text
export/sqlite/session.sqlite
```

The SQLite database contains `topics`, `messages`, and `exports` tables, plus one flattened per-topic table named from the sanitized topic path.

## Supported Export Formats

Implemented:

- `csv` for scalar and simple decoded structs
- `csv` point-row export for decoded `sensor_msgs/msg/PointCloud2`
- `csv`, `parquet`, `sqlite`, `jsonl`, `npz`, and `raw` remain available for image topics when tabular/raw analysis is useful
- `parquet` for flattened tabular topic data
- `sqlite` for a session database with metadata, message rows, and per-topic flattened tables
- `pcd` and `ply` point cloud sequences for decoded `sensor_msgs/msg/PointCloud2`
- `npz` compressed NumPy arrays for point clouds, image/depth frames, and numeric decoded messages
- `jsonl` for arbitrary decoded messages
- `png` and `jpg` image sequences for decoded `sensor_msgs/msg/Image` and `sensor_msgs/msg/CompressedImage`
- `mp4` video for decoded image topics, with a timestamp sidecar CSV
- `raw` for serialized CDR/message bytes with a timestamp sidecar CSV

Media formats `png`, `jpg`, and `mp4` are restricted to decoded ROS image topics such as `sensor_msgs/msg/Image` and `sensor_msgs/msg/CompressedImage`. Point cloud formats `pcd` and `ply` are restricted to decoded `sensor_msgs/msg/PointCloud2`. Data-oriented formats remain intentionally flexible across topic types.

## GUI Timeline Viewer

The optional GUI is a Windows-oriented, offline, view-only RViz2-like shell:

- Open a bag without playing it or subscribing to ROS.
- Use `File > Import bag...` to browse directly for a bag folder, or drag and drop a bag folder or supported bag file onto the window to open it.
- Use `File > Export...` to export selected topics through the same compatibility rules used by the CLI.
- Use `File > Version...` to view the installed version, local changelog, GitHub update status, release notes for newer versions, and the GUI upgrade action. Update checks and upgrades run as GUI background jobs.
- Use the Dark mode switch in `File > Version...` to choose light or dark GUI colors.
- Use the `Windows` menu to show or hide dockable panels such as `Topic list`, `Main view`, `Properties`, and `Output`.
- Move, float, tab, or close GUI panels using normal Qt dock-window behavior. All panels open by default and can be restored from the `Windows` menu.
- On first GUI startup, choose whether to check for updates, auto-update from GitHub releases, or turn the startup update checker off.
- Show a folded-by-default topic tree with category and message count.
- Drag topics from the topic tree into the main view.
- Scrub a timeline and preview assigned topics near the current timestamp.
- Change playback speed with the timeline rate selector: `0.25x`, `0.5x`, `1x`, `2x`, or `4x`.
- Preview image topics, point cloud topics, and scalar/custom message summaries.
- Render an image topic before playback, then use Play/Pause to play from a bounded rendered preview cache instead of decoding every frame on the timer.
- Show GUI progress while opening bags, rendering image playback caches, and exporting topics.
- Resize dock panels and topic-list columns after import/show/hide using bounded, eased resize transitions.
- Right-click a view to split horizontally or vertically, up to a 4x4 grid.
- Each view tile has a title and a slim top bar for rendering, maximizing/restoring, deleting, or opening the view as a pop-out window.
- Save non-destructive display/export settings to `ros2unbag_session.json`.

Install GUI dependencies with:

```powershell
py -m pip install -e .[gui]
```

Run:

```powershell
ros2unbag gui .\my_bag
```

From inside the interactive shell:

```text
ros2unbag> gui
ros2unbag> gui .\my_bag
```

The GUI does not rewrite bag files. It stores view settings such as visibility, color, opacity, point size, decimation, sync offset, and export preference in the sidecar JSON file.

The GUI preview path is optimized for responsive scrubbing: slider updates are debounced for manual scrubbing, but playback updates visible panes immediately on each timer tick. For image playback, the view renders display-sized frames into a bounded playback window and refreshes that window as playback advances, avoiding an unbounded full-topic frame cache. Dock panels and topic columns are resized after import and when panels are shown/hidden; the unused center spacer is collapsed so the main view can use the available workspace. The main view, topic list, properties panel, output panel, dialogs, and controls follow the selected light or dark theme. Lossless exports still use the dedicated exporter commands and are not affected by preview scaling.

## Project Structure

```text
.
|- .github/
|- .gitignore
|- CHANGELOG.md
|- CONTRIBUTING.md
|- LICENSE
|- README.md
|- SECURITY.md
|- pyproject.toml
|- ros2unbag/
`- tests/
```

The source package contains `cli/`, `core/`, `exporters/`, and `gui/` packages. The GUI package contains the optional PySide6 timeline viewer and its renderer adapters.

## Known Limitations

- This is an offline bag reader, not a live subscriber, recorder, or `ros2 bag play` wrapper.
- A bag usually does not identify exact publisher/subscriber node graph relationships. The tool may infer likely processing categories from names, types, and timestamps, but it must not claim exact graph relationships unless graph metadata was separately recorded.
- The SQLite fallback backend does not deserialize messages. Use the `rosbags` backend for decoded CSV, JSONL, image, and video exports.
- Image decoding currently supports `rgb8`, `bgr8`, `rgba8`, `bgra8`, `mono8`, `8UC1`, `mono16`, `16UC1`, and `32FC1` for `sensor_msgs/msg/Image`. Unsupported encodings are skipped with warnings instead of stopping the export.
- Compressed image decoding relies on OpenCV `cv2.imdecode`.
- MP4 writing relies on OpenCV `cv2.VideoWriter`; codec support can vary by Python/OpenCV/platform combination.
- MP4 export currently supports constant-FPS output only. Use the generated timestamp CSV for true ROS timing.
- SQLite export stores flattened message rows. Complex nested values that do not map cleanly to scalar columns are stored as JSON strings.
- The GUI timeline viewer is intentionally view-only and early-stage. It is not a full RViz2 replacement and does not provide live ROS node graph introspection.
- GUI image playback uses a bounded rendered preview cache. This improves Play/Pause responsiveness while limiting memory growth, but very large or high-resolution topics can still pause briefly when the playback window refreshes.
- GUI splitting is currently limited to a 4x4 view grid.
- The optional 3D point cloud renderer depends on VisPy/OpenGL support. If the renderer cannot initialize, the GUI falls back to non-3D preview text instead of failing the whole viewer.
- Progress totals depend on message counts reported by the bag backend. If a backend cannot provide a count, `ros2unbag` shows an indeterminate activity display instead of a percentage.
- Custom message support depends on what `rosbags` can deserialize from bag metadata. A future CLI option may accept custom `.msg` or `.idl` definition paths.
- ROS bags may contain camera images, sensor recordings, paths, or other private lab data. Review exported files before sharing them.

## Development Disclosure

This project was developed with significant AI assistance, including code generation, refactoring, and documentation support. The AI coding agent used during development was Codex5.5. Final integration, testing, code review, and release approval were performed by Owen Zi-Wen ZHOU. This review should not be interpreted as a professional security audit or production-level code audit. Issues, bug reports, and improvement suggestions are welcome.

## Affiliation / Reference

Maintainer: Owen Zi-Wen ZHOU

Affiliation: Sophia University | Control Engineering / AI Formula

Related laboratory reference: [SophiaControl/AIformula_sophia](https://github.com/SophiaControl/AIformula_sophia)

This repository is personally maintained by Owen Zi-Wen ZHOU. The SophiaControl/AIformula_sophia repository is included only as a related laboratory reference. This should not be interpreted as a dependency, endorsement, official maintenance, publication, or ownership claim by Sophia University, the Control Laboratory, Honda, or the AI Formula project.

## Contributing

Small bug reports, edge-case notes, and focused pull requests are welcome. Please see [CONTRIBUTING.md](CONTRIBUTING.md).

Please do not attach private ROS bags or lab data to public issues unless you have reviewed and sanitized them.

## License

This project is released under the GNU Affero General Public License v3.0 or later
(`AGPL-3.0-or-later`). See [LICENSE](LICENSE).
