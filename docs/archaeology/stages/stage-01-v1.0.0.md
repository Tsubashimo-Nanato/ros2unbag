# Stage 1: v1.0.0

## Observed facts

- Commit `0e69724`, subject `Prepare initial public release`.
- Top-level structure included `.github`, `ros2_unbag`, `tests`, `README.md`, `CHANGELOG.md`, `pyproject.toml`, and community files.
- Package import name was `ros2_unbag`; installed command was `ros2unbag`.
- Exporters present included CSV, JSONL, raw, image sequence, and MP4 video support.

## Inferred purpose

- This appears to be the first public CLI release for offline ROS bag inspection on Windows.
- Parquet, SQLite, and GUI work were planned but not implemented at this stage.

## Main components

- Core/domain logic: bag readers, decoding, manifests, topic indexing, classification, sync, point-cloud helpers.
- CLI layer: Typer CLI plus interactive REPL.
- GUI layer: reserved package only.
- Tests: 29 passing pytest tests.
- Docs: README, changelog, contributing, security, license, issue templates.

## Build/test status

- Command attempted: `py -m pytest --tb=short`.
- Result: passed, 29 tests.

## Notes

- Core logic and CLI orchestration were already separated, but `Session` was the central workflow object.
- Planned exporters were represented in docs/code before implementation.
