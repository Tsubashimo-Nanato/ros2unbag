# ros2unbag

[![Release](https://img.shields.io/badge/release-v1.6.1-f59e0b)](https://github.com/Tsubashimo-Nanato/ros2unbag/releases)
![Python](https://img.shields.io/badge/python-3.10--3.13-3776ab)
[![License](https://img.shields.io/badge/license-AGPL--3.0--or--later-4c1)](LICENSE)
![GUI](https://img.shields.io/badge/GUI-active_development-ef4444)

Open ROS 1/2 bags on Windows, inspect what is inside, and export the useful parts without first turning your workstation into a temporary ROS installation.

`ros2unbag` is an offline, read-only bag inspector and exporter. It provides a CLI, an interactive shell, and a PySide6 timeline viewer for images, lane-line point clouds, topic metadata, and synchronized previews.

![ros2unbag Timeline Viewer](docs/media/gui-timeline.png)

> [!NOTE]
> The CLI and exporters are usable today. The GUI is under active development: expect regular interaction and rendering improvements, and please report the awkward edges while they are still easy to move.

## Quick Start

```powershell
git clone https://github.com/Tsubashimo-Nanato/ros2unbag.git
cd ros2unbag
py -m pip install -e .[gui]

ros2unbag topics .\my_bag
ros2unbag gui .\my_bag
```

Windows helpers are also included:

```bat
install.bat
install.bat gui
```

Restart the terminal after `install.bat` if the `ros2unbag` command is not immediately available.

## What It Does

| Area | Practical use |
| --- | --- |
| Inspect | Topic tree, detailed scan, message counts, durations, timestamps, and nearest-message lookup |
| Export | CSV, Parquet, SQLite, JSONL, NPZ, raw CDR, PNG/JPG, MP4, PCD, and PLY |
| Explore | Interactive shell with history, topic completion, and selected-export queues |
| Visualize | Timeline scrubbing, image playback, split views, lane-line overlays, point-cloud previews, and light/dark themes |
| Stay offline | Read rosbag1 and rosbag2 through `rosbags`; fall back to SQLite for raw ROS 2 access |

Bag files are never rewritten. GUI settings can be stored in a sidecar JSON file, while lossless exports stay on their dedicated exporter path.

## Real Bag, Real Frames

The following 2x2 was generated at one timeline position from the local validation bag. It combines the RGB camera, annotated perception output, binary mask, and three lane-line `PointCloud2` topics.

![Four synchronized views from the validation bag](docs/media/validation-run-2x2.png)

The same run in motion:

![Annotated and binary mask animation](docs/media/validation-run.gif)

[Open the MP4 preview](docs/media/validation-run.mp4) if GIF timing is not your preferred scientific instrument.

The 2x2 image, GIF, and MP4 were generated directly from the bag by Codex using shell mode. No synthetic road scene or hand-drawn lane data was substituted.

## Common Commands

Start the interactive shell:

```powershell
ros2unbag
```

A short session looks like this:

```text
ros2unbag> open .\my_bag
ros2unbag> topics
ros2unbag> scan --all
ros2unbag> inspect --time 22.2 --dur /camera/image_raw
ros2unbag> export /camera/image_raw --format mp4 --fps 30 --out .\export
ros2unbag> export /points --format pcd --out .\export
ros2unbag> gui
```

The same operations are available as direct commands:

```powershell
ros2unbag scan .\my_bag --out .\scan
ros2unbag export .\my_bag --topic /imu --format parquet --out .\export
ros2unbag export .\my_bag --topic /camera/image_raw --format png --out .\export
ros2unbag export .\my_bag --topic /points --format ply --out .\export
ros2unbag export-all .\my_bag --out .\export
```

Upgrade an installed copy with:

```powershell
ros2unbag upgrade --yes
```

## Export Notes

- Image and video exports support decoded `sensor_msgs/msg/Image` and `sensor_msgs/msg/CompressedImage` topics.
- PCD and PLY preserve supported numeric `PointCloud2` fields such as `x`, `y`, `z`, `intensity`, `rgb`, `ring`, and `time`.
- MP4 uses constant-FPS playback and writes the original ROS timestamps to a sidecar CSV.
- PNG/JPG, point-cloud sequences, NPZ sequences, MP4, and raw exports include timestamp sidecars where applicable.
- Unsupported or undecoded custom messages can still be exported as raw serialized data.

## GUI Development

The timeline viewer is a Windows-oriented, offline visualization workspace. Current work focuses on predictable topic assignment, split views, bounded image playback caches, lane-line and point-cloud navigation, and dock behavior that does not require a wrestling match.

It is intentionally view-only: this is not a live ROS subscriber, recorder, node-graph inspector, or full RViz2 replacement. The optional 3D point-cloud renderer also depends on working VisPy/OpenGL support; the rest of the application remains usable without it.

Run the GUI directly:

```powershell
ros2unbag gui .\my_bag
```

## Sample Data Provenance

The example bag used for the media above was produced with the open [aiformula-support/aiformula](https://github.com/aiformula-support/aiformula) stack during a validation run by [SophiaControl/AIformula_sophia](https://github.com/SophiaControl/AIformula_sophia).

Background on the outdoor autonomous-driving program is available from the [AI Formula development page](https://sites.google.com/p.chibakoudai.jp/rdc-lab/development/ai-formula). The bag is local debug data and is not distributed in this repository.

These references describe data provenance and project context. They do not imply that the linked organizations maintain, endorse, or audit `ros2unbag`.

## Known Limits

- Image decoding currently covers common RGB/BGR/RGBA/BGRA, mono8/16, `16UC1`, and `32FC1` encodings.
- Codec availability for MP4 varies by OpenCV build and platform.
- The SQLite fallback cannot deserialize CDR messages; use the `rosbags` backend for decoded exports.
- Custom message support depends on definitions available to `rosbags` from the bag metadata.
- Large, high-resolution GUI image topics can pause briefly when a bounded playback window refreshes.
- Bags may contain private camera, sensor, map, or laboratory data. Review exports before publishing them.

## Development Disclosure

This project has received significant AI assistance for implementation, refactoring, testing, documentation, and the shell-mode media workflow shown above. Final integration, review, and release approval remain the maintainer's responsibility; that review is not a professional security audit.

Maintainer: Owen Zi-Wen ZHOU<br>
Affiliation: Sophia University, Control Engineering / AI Formula

## Contributing

Focused bug reports, edge-case notes, and small pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md). Please do not attach private bags to public issues unless they have been reviewed and sanitized.

## License

`ros2unbag` is released under `AGPL-3.0-or-later`. See [LICENSE](LICENSE).
