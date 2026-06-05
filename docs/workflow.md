# Development Workflow

## Branching

- `main` should remain the stable branch.
- Work should happen on topic branches such as `feature/*`, `fix/*`, `test/*`, `docs/*`, `refactor/*`, or `chore/*`.
- Use `legacy/*` branches for preserved historical snapshots from old tags.
- Use `archaeology/*` branches for reconstructed historical review branches.

## Pull Requests

Each PR should include:

- Summary of behavior or documentation changes.
- Test commands and results.
- Screenshots or logs for GUI/terminal behavior when relevant.
- Notes about compatibility or migration risk.

Prefer small PRs with one clear purpose. Avoid mixing archaeology docs, refactors, and behavior changes unless there is a strong reason.

## Tags

- Tags should be used for deliberate release milestones.
- Old tags are preserved for now as historical snapshots.
- Future backup needs should use normal commits, branches, or external backups instead of accidental release-style tags.
- Do not delete old tags without a separate backup/export and explicit approval.

## Local Safety

- Check `git status --short` before switching branches or applying reconstructed patches.
- Do not rewrite history for archaeology work.
- Do not force-push.
- Do not delete remote branches.
- Keep generated ROS bag exports, large bag data, and local histories ignored.

## Suggested Release Flow

1. Create a branch from `main`.
2. Make small commits with tests.
3. Open a PR into `main`.
4. Merge after review and passing tests.
5. Create a release tag only when intentionally releasing.
6. Push the tag after the release commit is final.
