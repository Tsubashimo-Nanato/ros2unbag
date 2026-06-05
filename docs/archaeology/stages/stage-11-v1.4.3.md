# Stage 11: v1.4.3

## Observed facts

- Commit `7fc8d6e`, subject `Release 1.4.3 shell upgrade`.
- Added `ros2unbag/cli/upgrade.py` and `tests/test_upgrade.py`.
- README/changelog describe upgrade command support and Windows progress fallback.

## Inferred purpose

- This stage added self-update workflow support and hardened Windows console output.

## Main components

- CLI/shell layer: `upgrade` command and `--ref` support.
- Core/domain logic: unchanged for bag processing.
- Tests: 68 passing pytest tests.

## Build/test status

- Command attempted: `py -m pytest --tb=short`.
- Result: passed, 68 tests.

## Notes

- Upgrade logic is platform-sensitive and should remain isolated from core bag processing.
- Network/pip behavior is represented by tests rather than live upgrade execution.
