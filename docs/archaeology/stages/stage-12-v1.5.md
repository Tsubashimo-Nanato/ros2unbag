# Stage 12: v1.5

## Observed facts

- Commit `c6277ed`, subject `Release v2.0.0`.
- Tag name is `v1.5`; package metadata and changelog section report version `1.5`.
- Added Windows batch helpers, optional GUI shell, preview/update helpers, NPZ export, PCD/PLY export, and GUI tests.
- This was the largest observed transition by changed files and insertions.

## Inferred purpose

- This appears to be the first broad GUI/native-export stage, despite the ambiguous commit subject.
- The project expanded from CLI/shell tooling into a Windows desktop inspection shell.

## Main components

- Core/domain logic: preview API, update checks, jobs/cancellation primitives.
- Export layer: NPZ, PCD, and PLY exporters.
- CLI/shell layer: GUI command and launcher scripts.
- GUI layer: PySide6 timeline viewer shell and render helpers.
- Tests: 87 passing pytest tests.

## Build/test status

- Command attempted: `py -m pytest --tb=short`.
- Result: passed, 87 tests.

## Notes

- GUI code introduced the highest coupling and review risk.
- Version-label ambiguity should be preserved in docs rather than corrected retroactively.
