# Tag Inventory

All tags observed during inventory were lightweight tags pointing directly to commits. Tagger dates were therefore unavailable.

| Stage | Tag | Type | Commit | Commit date | Subject | Reachable from main | Local legacy branch | Test result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 01 | `v1.0.0` | lightweight | `0e69724` | 2026-04-28 15:18 +0900 | Prepare initial public release | yes | `legacy/stage-01-v1.0.0` | 29 passed |
| 02 | `v1.2.0` | lightweight | `58e7d89` | 2026-05-06 07:57 +0900 | Release v1.2.0 | yes | `legacy/stage-02-v1.2.0` | 32 passed |
| 03 | `v1.2.2` | lightweight | `65491c9` | 2026-05-11 07:52 +0900 | Release v1.2.2 | yes | `legacy/stage-03-v1.2.2` | 38 passed |
| 04 | `v1.3.0` | lightweight | `b5ea5a7` | 2026-05-12 16:08 +0900 | Release v1.3.0 | yes | `legacy/stage-04-v1.3.0` | 39 passed |
| 05 | `v1.3.1` | lightweight | `d90a793` | 2026-05-12 21:39 +0900 | Release v1.3.1 | yes | `legacy/stage-05-v1.3.1` | 40 passed |
| 06 | `v1.3.2` | lightweight | `67df918` | 2026-05-14 13:34 +0900 | Release v1.3.2 | yes | `legacy/stage-06-v1.3.2` | 45 passed |
| 07 | `v1.3.4` | lightweight | `fb8f797` | 2026-05-14 14:06 +0900 | Release v1.3.4 | yes | `legacy/stage-07-v1.3.4` | 50 passed |
| 08 | `v1.4.0` | lightweight | `d550b66` | 2026-05-14 14:22 +0900 | Release v1.4.0 | yes | `legacy/stage-08-v1.4.0` | 55 passed |
| 09 | `v1.4.1` | lightweight | `594f12f` | 2026-05-14 19:50 +0900 | Release v1.4.1 | yes | `legacy/stage-09-v1.4.1` | 56 passed |
| 10 | `v1.4.2` | lightweight | `64925ba` | 2026-05-14 19:58 +0900 | Release v1.4.2 | yes | `legacy/stage-10-v1.4.2` | 59 passed |
| 11 | `v1.4.3` | lightweight | `7fc8d6e` | 2026-05-18 10:12 +0900 | Release 1.4.3 shell upgrade | yes | `legacy/stage-11-v1.4.3` | 68 passed |
| 12 | `v1.5` | lightweight | `c6277ed` | 2026-05-24 15:16 +0900 | Release v2.0.0 | yes | `legacy/stage-12-v1.5` | 87 passed |
| 13 | `v1.5.1` | lightweight | `efce8f4` | 2026-05-24 20:13 +0900 | Release v1.5.1 GUI polish | yes | `legacy/stage-13-v1.5.1` | 90 passed |
| 14 | `v1.5.2` | lightweight | `9e14b2e` | 2026-06-06 04:41 +0900 | Release v1.5.2 | yes | `legacy/stage-14-v1.5.2` | 96 passed |

## Ambiguities

- `v1.5` is the only observed version-label ambiguity. The tag name is `v1.5`, package metadata reports `1.5`, and changelog section is `[1.5]`, but the commit subject says `Release v2.0.0`.
- Tags `v1.2.1`, `v1.3.3`, and semver-style `v1.5.0` are absent. This is observed fact, not evidence of missing commits.
