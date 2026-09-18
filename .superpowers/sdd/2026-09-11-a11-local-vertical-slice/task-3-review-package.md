# Task 3 Independent Review Package

Review Task 3 as a direct complete-file review because Git is intentionally unavailable. Do not edit files and do not spawn subagents.

## Requirements

- `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-3-brief.md`
- `docs/superpowers/plans/2026-09-11-a11-local-vertical-slice.md` Task 3
- `docs/superpowers/specs/2026-09-11-a11-local-vertical-slice-design.md` sections 4.1, 7.2, and 9
- `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/progress.md`

## Implementation

- `backend/alembic.ini`
- `backend/migrations/env.py`
- `backend/migrations/versions/0001_initial.py`
- `backend/src/hw_review/domain/models.py`
- `backend/src/hw_review/domain/__init__.py`
- `backend/src/hw_review/persistence/__init__.py`
- `backend/src/hw_review/persistence/database.py`
- `backend/src/hw_review/persistence/tables.py`
- `backend/src/hw_review/persistence/repositories.py`
- `backend/tests/integration/test_sqlite_repository.py`
- `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-3-report.md`

## Claimed evidence

- Initial missing-feature RED plus serializer and update-method TDD cycles are recorded in the report.
- Fresh migration created exactly seven application tables plus `alembic_version`, version `0001`; `alembic check` found no diff.
- Focused integration suite: 12 passed. Full backend suite: 84 passed.
- Verification DB was removed; no real samples and no Git were used.

## Review priorities

1. Migration and SQLAlchemy metadata match and runtime never creates schema.
2. Every SQLite connection enforces foreign keys; schema has the required foreign keys, check constraints, and two unique identities.
3. Task and 21 results fully survive close/reopen, with precise enum/timestamp/nested evidence round trip.
4. `replace_all` is atomic and targets the intended active revision only; errors cannot erase the previous valid set.
5. Revision numbering and snapshot creation are transactionally coherent, snapshots contain the intended complete result/decision facts, remain immutable, and uniqueness conflicts map predictably.
6. UTC and deterministic TEXT JSON boundaries are correct; SQLite JSON operators are absent.
7. Domain models are frozen and validated without weakening Task 1/2 contracts.
8. Later Task 7 can use these repositories without bypassing interfaces or relying on SQLite-specific behavior in business services.

You may rerun tests with bundled Python and a fresh `--basetemp` under `backend/.pytest-tmp/`.

## Required response

Return findings ordered Critical, Important, Minor with exact file/line references. Then return separate verdicts:

- `Spec compliance: PASS|FAIL`
- `Task quality: PASS|FAIL`

If a verdict fails, give the minimum concrete code and test fixes. Ignore style-only preferences.
