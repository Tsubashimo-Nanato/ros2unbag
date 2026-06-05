# Stage 4: v1.3.0

## Observed facts

- Commit `b5ea5a7`, subject `Release v1.3.0`.
- Package directory was renamed from `ros2_unbag` to `ros2unbag`.
- Added `ros2unbag/cli/progress.py` and `ros2unbag/core/progress.py`.
- Removed the `tqdm` runtime dependency and kept Rich.

## Inferred purpose

- This stage aligned distribution, command, and import package naming.
- It also introduced shared progress callback plumbing for future long-running operations.

## Main components

- Core/domain logic: package rename plus shared progress abstraction.
- CLI layer: progress rendering introduced.
- Tests: 39 passing pytest tests.
- Docs: README updated for package-name consistency.

## Build/test status

- Command attempted: `py -m pytest --tb=short`.
- Result: passed, 39 tests.

## Notes

- The package rename is a high-impact compatibility event.
- Tests were updated across imports, reducing migration risk.
