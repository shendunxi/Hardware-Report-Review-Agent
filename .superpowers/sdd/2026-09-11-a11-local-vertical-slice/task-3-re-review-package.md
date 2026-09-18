# Task 3 Scoped Re-review Package — fix round 1/5

Review only the three prior Important findings and whether the fixes introduce any new Critical or Important defect. Do not edit files and do not spawn subagents.

## Prior findings

1. Manual decisions could not persist before completion and therefore could not survive restart or be replaced during active review.
2. `replace_all()` accepted result rows for a future or stale non-active task revision, creating invisible orphan results.
3. `complete()` accepted duplicate/conflicting decisions for one rule result and the schema lacked the matching uniqueness guarantee.

## Claimed fixes

- `RepositoryBundle.decisions` exposes a typed active-revision decision repository supporting save-or-replace and list/current behavior. Draft decisions survive restart, can be replaced while active, and become associated/frozen atomically on completion.
- `manual_decisions` now includes task and active revision identity, nullable pre-completion `revision_id`, uniqueness for one decision per task/result/active revision, and uniqueness for one result per completed revision.
- `replace_all()` loads task activity in the same transaction before deleting and requires all result revisions to equal the actual active revision. Future/stale conflicts leave the previous result set unchanged.
- `complete()` rejects duplicate `rule_result_id` inputs before writes and atomically freezes the authoritative set; conflict probes prove no revision or partial association remains.
- Fresh migration version `0001` still creates the same seven application tables plus Alembic version; metadata check is clean. Focused: 18 passed. Full: 90 passed. Final verification: 90 passed.

## Inspect

- `backend/migrations/versions/0001_initial.py`
- `backend/src/hw_review/domain/models.py`
- `backend/src/hw_review/domain/ports.py`
- `backend/src/hw_review/persistence/tables.py`
- `backend/src/hw_review/persistence/repositories.py`
- `backend/tests/integration/test_sqlite_repository.py`
- `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-3-report.md`

## Required response

For each finding return `ADDRESSED` or `OPEN` with exact file/line evidence; report new Critical or Important issues; then:

- `Spec compliance: PASS|FAIL`
- `Task quality: PASS|FAIL`
