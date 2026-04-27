# ros2unbag

`ros2unbag` is a Python-first command-line tool for inspecting ROS bag files offline. It reads bags without playing them, lists topics and message types, builds timestamp indexes, classifies topics into practical export categories, and exports selected data into Windows-readable formats.

## Status

Current release target: `v1.0.0`

Release preparation date: 2026-04-28

This project is currently in an initial public release state. The core workflow is usable, but some features are incomplete and edge cases may not yet be handled.

Reviewed and released by Owen ZiWen Zhou. The maintainer is an amateur developer, and issues may remain. Bug reports and suggestions are welcome.

## Features

- Offline ROS bag inspection without `ros2 bag play`.
- Preferred `rosbags` backend for reading rosbag1/rosbag2 data without requiring a full ROS installation.
- SQLite fallback backend for basic ROS 2 `.db3` scans and raw exports when decoded message support is unavailable.
- Topic table, namespace tree, and interactive topic navigation views.
- Timestamp indexing and nearest-message inspection by bag-relative time.
- Topic duration reporting with bag-relative start/end coverage.
- CSV export for scalar/simple decoded messages and decoded `sensor_msgs/msg/PointCloud2` point rows.
- JSONL export for arbitrary decoded messages.
- PNG/JPG image sequence export for supported decoded image topics.
- MP4 export for decoded image topics using constant FPS.
- Timestamp sidecar CSV files for image, video, and raw exports.
- Raw serialized dumps for unsupported or undecoded topics.
- Interactive REPL shell with command history and tab completion.

## Installation

From this repository:

```powershell
py -m pip install -e .
```

For development:

```powershell
py -m pip install -e .[dev]
```

For future GUI experiments:

```powershell
py -m pip install -e .[gui]
```

The distribution name is `ros2unbag`, the installed command is `ros2unbag`, and the Python import package is `ros2_unbag`.

Uninstall:

```powershell
ros2unbag uninstall --yes
```

Preview the exact uninstall command:

```powershell
ros2unbag uninstall --print-only
```

If `ros2unbag` is not on `PATH`, use Python directly:

```powershell
py -m ros2_unbag.cli.main uninstall --yes
```

## Usage

Scan a bag and print the topic table:

```powershell
ros2unbag scan .\my_bag
```

The default scan view is a compact table. The first column is the topic leaf name, such as `cmd_vel`, and the second column is the parent topic path, such as `/aiformula_control/game_pad`.

Other scan views:

```powershell
ros2unbag scan .\my_bag --view table
ros2unbag scan .\my_bag --view tree
ros2unbag scan .\my_bag --view nav
```

Use `--view tree` to see the topic namespace structure. Use `--view nav` for an interactive browser where you enter `1`, `2`, `3`, etc. to open a namespace or topic, `b` / `back` to go up, and `q` / `quit` to exit.

Scan and write `manifest.json` and `topics.csv`:

```powershell
ros2unbag scan .\my_bag --out .\exported_scan
```

Export one topic:

```powershell
ros2unbag export .\my_bag --topic /imu --format csv --out .\export
ros2unbag export .\my_bag --topic /diagnostics --format jsonl --out .\export
ros2unbag export .\my_bag --topic /camera/image_raw --format png --out .\export
ros2unbag export .\my_bag --topic /camera/image_raw --format jpg --out .\export
ros2unbag export .\my_bag --topic /camera/image_raw --format mp4 --fps 30 --out .\export
ros2unbag export .\my_bag --topic /unknown/custom_topic --format raw --out .\export
```

Export all compatible topics using default implemented formats:

```powershell
ros2unbag export-all .\my_bag --out .\export
```

Inspect nearest messages at 145 seconds after bag start:

```powershell
ros2unbag inspect .\my_bag --time 145.0
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

Typer shell completion is available:

```powershell
ros2unbag --install-completion powershell
ros2unbag --show-completion powershell
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
ros2unbag> scan
ros2unbag> topics
ros2unbag> dur /aiformula_perception/lane_line_publisher/lane_lines/center
ros2unbag> inspect --time 25.0
ros2unbag> export /aiformula_control/joy --format csv --out .\export
ros2unbag> export /camera/image_raw --format mp4 --fps 30 --out .\export
ros2unbag> export-all --out .\export
ros2unbag> close
ros2unbag> exit
```

Interactive commands:

- `open BAG_PATH`
- `scan [BAG_PATH]`
- `topics`
- `dur TOPIC`
- `export TOPIC --format csv|png|jpg|mp4|jsonl|raw --out OUT_DIR [--fps FPS]`
- `export-all --out OUT_DIR`
- `inspect --time SECONDS`
- `close`
- `help`
- `clear`
- `exit` / `quit`

The REPL uses `prompt-toolkit`. Tab completes command names, options such as `--format`, `--out`, `--time`, and filesystem paths. After `open BAG_PATH`, Tab also completes topic names from the opened bag. Press Tab twice to show possible completions. History is stored in `.ros2unbag_history` in the current working directory and is ignored by Git.

## Example Workflow

```powershell
py -m pip install -e .
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

Timestamp CSV sidecars include the source ROS timestamp in nanoseconds and `timestamp_sec_from_start` relative to the bag start. Image and video sidecars also include frame index, dimensions, encoding, and output filename or video time.

## Supported Export Formats

Implemented:

- `csv` for scalar and simple decoded structs
- `csv` point-row export for decoded `sensor_msgs/msg/PointCloud2`
- `jsonl` for arbitrary decoded messages
- `png` / `jpg` image sequences for decoded `sensor_msgs/msg/Image` and `sensor_msgs/msg/CompressedImage`
- `mp4` video for decoded image topics, with a timestamp sidecar CSV
- `raw` for serialized CDR/message bytes with a timestamp sidecar CSV

Recognized but not implemented:

- `parquet`
- `sqlite`

## Project Structure

```text
.
├── .github/
├── .gitignore
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
├── README.md
├── SECURITY.md
├── pyproject.toml
├── ros2_unbag/
└── tests/
```

The source package contains `cli/`, `core/`, `exporters/`, and an intentionally reserved `gui/` package for the future PySide6 timeline viewer. `parquet_exporter.py` and `sqlite_exporter.py` are reserved for planned export formats.

## Known Limitations

- This is an offline bag reader, not a live subscriber, recorder, or `ros2 bag play` wrapper.
- A bag usually does not identify exact publisher/subscriber node graph relationships. The tool may infer likely processing categories from names, types, and timestamps, but it must not claim exact graph relationships unless graph metadata was separately recorded.
- The SQLite fallback backend does not deserialize messages. Use the `rosbags` backend for decoded CSV, JSONL, image, and video exports.
- Image decoding currently supports `rgb8`, `bgr8`, `rgba8`, `bgra8`, `mono8`, and `8UC1` for `sensor_msgs/msg/Image`. Unsupported encodings are skipped with warnings instead of stopping the export.
- Compressed image decoding relies on OpenCV `cv2.imdecode`.
- MP4 writing relies on OpenCV `cv2.VideoWriter`; codec support can vary by Python/OpenCV/platform combination.
- MP4 export currently supports constant-FPS output only. Use the generated timestamp CSV for true ROS timing.
- Parquet, SQLite, and GUI features are not implemented yet.
- Custom message support depends on what `rosbags` can deserialize from bag metadata. A future CLI option may accept custom `.msg` or `.idl` definition paths.
- ROS bags may contain camera images, sensor recordings, paths, or other private lab data. Review exported files before sharing them.

## Development Disclosure

This project was developed with significant AI assistance, including code generation, refactoring, and documentation support. The AI coding agent used during development was Codex5.5. Final integration, testing, code review, and release approval were performed by Owen ZiWen Zhou. This review should not be interpreted as a professional security audit or production-level code audit. Issues, bug reports, and improvement suggestions are welcome.

## Affiliation / Reference

Maintainer: Owen ZiWen Zhou

Affiliation: Sophia University | Control Engineering / AI Formula

Related laboratory reference: [SophiaControl/AIformula_sophia](https://github.com/SophiaControl/AIformula_sophia)

This repository is personally maintained by Owen ZiWen Zhou. The SophiaControl/AIformula_sophia repository is included only as a related laboratory reference. This should not be interpreted as a dependency, endorsement, official maintenance, publication, or ownership claim by Sophia University, the Control Laboratory, Honda, or the AI Formula project.

## Contributing

Small bug reports, edge-case notes, and focused pull requests are welcome. Please see [CONTRIBUTING.md](CONTRIBUTING.md).

Please do not attach private ROS bags or lab data to public issues unless you have reviewed and sanitized them.

## License

This project is released under the MIT License. See [LICENSE](LICENSE).
