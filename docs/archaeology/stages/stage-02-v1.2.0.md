# Stage 2: v1.2.0

## Observed facts

- Commit `58e7d89`, subject `Release v1.2.0`.
- Added `ros2_unbag/exporters/tabular.py` and `tests/test_phase4_exports.py`.
- Parquet and SQLite exports were implemented and wired into `Session`.
- README and changelog describe this as the Phase 4 tabular export release.

## Inferred purpose

- This stage promoted planned tabular storage formats into working export paths.
- The project moved from basic inspection/export to richer analysis-friendly outputs.

## Main components

- Core/domain logic: unchanged overall structure with `Session` coordinating exports.
- Export layer: CSV began sharing flattened tabular collection with Parquet and SQLite.
- CLI/shell layer: REPL help listed `parquet` and `sqlite`.
- Tests: 32 passing pytest tests.
- Docs: README and changelog updated for implemented tabular formats.

## Build/test status

- Command attempted: `py -m pytest --tb=short`.
- Result: passed, 32 tests.

## Notes

- Shared tabular collection reduced CSV/Parquet/SQLite duplication.
- SQLite and Parquet behavior had targeted tests but remained exporter-owned.
