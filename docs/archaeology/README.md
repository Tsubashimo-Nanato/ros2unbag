# Repository Archaeology

This directory records a local-only reconstruction of the repository history from tags.

## Scope

- Existing tags were preserved as historical snapshots.
- Local `legacy/*` branches were created to make each tag easier to inspect.
- Local `archaeology/transition-*` branches were created as synthetic, PR-style transition branches.
- These transition branches are reconstructed review aids, not the original development history.
- No remote branches were changed and no tags were deleted, renamed, or recreated.

## Repository Inventory

- Primary language: Python.
- Project type: Windows-oriented ROS/ROS2 bag inspection and export CLI with an optional PySide6 GUI shell.
- Build system: Hatchling via `pyproject.toml`.
- Package manager: `pip`.
- Test system: `pytest`, configured in `pyproject.toml`.
- Entry points: `ros2unbag = "ros2unbag.cli.main:app"`, `ros2unbag.bat`, and `install.bat`.
- Current package layout: `ros2unbag/core`, `ros2unbag/exporters`, `ros2unbag/cli`, and `ros2unbag/gui`.
- Existing docs: `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`, and this `docs/` tree.
- Existing GitHub configuration: issue templates under `.github/ISSUE_TEMPLATE`.
- Missing GitHub configuration observed at inventory time: no `.github/workflows` CI configuration.
- GitHub CLI: unavailable locally, so issues and PRs were not inspected.

## Chronological Tags

The observed chronological order is:

1. `v1.0.0`
2. `v1.2.0`
3. `v1.2.2`
4. `v1.3.0`
5. `v1.3.1`
6. `v1.3.2`
7. `v1.3.4`
8. `v1.4.0`
9. `v1.4.1`
10. `v1.4.2`
11. `v1.4.3`
12. `v1.5`
13. `v1.5.1`
14. `v1.5.2`

The order matches commit topology and commit dates. One naming ambiguity exists: tag `v1.5` points to a commit whose subject says `Release v2.0.0`; the changelog and package metadata describe that stage as `1.5`.

## Files

- [tag-inventory.md](tag-inventory.md) lists tag metadata and test results.
- [branch-map.md](branch-map.md) maps tags to local legacy and transition branches.
- [stages/](stages/) contains one stage log per tag.
- [transitions/](transitions/) contains one transition log per adjacent tag pair.
