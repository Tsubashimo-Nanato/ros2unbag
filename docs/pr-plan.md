# Pull Request Plan

No remote PRs were opened. This plan prepares the local work for review.

## PR 1: Repository archaeology documentation

- Branch: `refactor/repository-organization`
- Purpose: add tag inventory, stage logs, transition logs, and branch map.
- Files likely changed: `docs/archaeology/**`.
- Risk: low; documentation only.
- Test commands: `py -m pytest`.
- Review notes: check that observed facts and inferred purpose are clearly separated.

## PR 2: Baseline tests and smoke tests

- Branch: `test/export-policy-characterization`
- Purpose: add tests around export policy behavior before deeper refactors.
- Files likely changed: `tests/test_export_policy.py`.
- Risk: low.
- Test commands: `py -m pytest`.
- Review notes: preserve existing import compatibility from `ros2unbag.core.session`.

## PR 3: Export policy extraction

- Branch: `refactor/export-policy`
- Purpose: move export format constants, validation, compatibility, defaults, and suggestions into `ros2unbag.core.export_policy`.
- Files likely changed: `ros2unbag/core/export_policy.py`, `ros2unbag/core/session.py`, `ros2unbag/core/type_classifier.py`.
- Risk: medium-low because export validation is user-facing.
- Test commands: `py -m pytest`.
- Review notes: verify CLI, REPL, and older import paths still work.

## PR 4: GUI shell decomposition

- Branch: `refactor/gui-view-models`
- Purpose: move GUI state and command orchestration out of widget event handlers where practical.
- Files likely changed: `ros2unbag/gui/**`, `tests/test_gui_timeline_viewer.py`.
- Risk: medium-high because GUI regressions are harder to catch in headless tests.
- Test commands: `py -m pytest`; manual GUI smoke test if PySide6 is available.
- Review notes: keep GUI behavior unchanged.

## PR 5: Session orchestration cleanup

- Branch: `refactor/session-services`
- Purpose: split selected export queueing, coverage warnings, and dispatch helpers into smaller testable services if the code keeps growing.
- Files likely changed: `ros2unbag/core/session.py`, focused new core modules, session tests.
- Risk: medium.
- Test commands: `py -m pytest`.
- Review notes: avoid changing CLI-visible behavior.

## PR 6: GitHub workflow finalization

- Branch: `chore/github-workflows`
- Purpose: add CI workflow, refine issue/PR templates, and document release procedure.
- Files likely changed: `.github/**`, `docs/workflow.md`, `README.md`.
- Risk: low-medium depending on CI environment.
- Test commands: local `py -m pytest`; remote CI once pushing is authorized.
- Review notes: no branch protection or remote settings should be changed in this repo pass.
