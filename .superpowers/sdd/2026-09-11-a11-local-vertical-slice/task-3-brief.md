# Task 3 Brief — SQLite schema, migrations, and lifecycle repositories

## Objective

Introduce restart-safe development persistence behind the Task 1 repository protocols. The schema must be created only by Alembic migration, preserve audit/history facts, enforce foreign keys and uniqueness, and round-trip immutable domain objects without relying on SQLite JSON operators.

## Source of truth

- Plan: `docs/superpowers/plans/2026-09-11-a11-local-vertical-slice.md`, Task 3.
- Design: `docs/superpowers/specs/2026-09-11-a11-local-vertical-slice-design.md`, sections 4.1, 7.2, and 9.
- Existing contracts: `backend/src/hw_review/domain/` and Task 2 `StagedFile`.
- Ledger: `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/progress.md`.

## Binding scope

- Development database is SQLite. Production database remains undecided; do not encode a production database decision.
- Use Alembic migrations; runtime repository construction must not call `create_all` or otherwise synthesize schema.
- Store timestamps in UTC and structured snapshots as deterministic JSON text serialized in repository code. Do not depend on SQLite JSON functions.
- Enable SQLite foreign keys on every connection.
- Do not implement parsers, rules, orchestration, HTTP endpoints, authentication, or frontend behavior.
- Do not use Git and do not access real report samples.
- Follow strict TDD: tests and observed RED first, then minimum implementation, then focused and full GREEN.

## Files

Create:

- `backend/alembic.ini`
- `backend/migrations/env.py`
- `backend/migrations/script.py.mako` only if Alembic requires it
- `backend/migrations/versions/0001_initial.py`
- `backend/src/hw_review/persistence/__init__.py`
- `backend/src/hw_review/persistence/database.py`
- `backend/src/hw_review/persistence/tables.py`
- `backend/src/hw_review/persistence/repositories.py`
- `backend/tests/integration/test_sqlite_repository.py`
- `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-3-report.md`

Modify only as needed:

- `backend/src/hw_review/domain/models.py`
- `backend/src/hw_review/domain/__init__.py`
- `backend/src/hw_review/domain/ports.py`
- `backend/pyproject.toml` only if package/test configuration is genuinely required.

Do not modify requirements, design, plan, prototype, staging/cleanup services, or Task 1/2 tests.

## Required schema

Migration `0001_initial` creates exactly these seven application tables (plus Alembic's version table):

1. `tasks`
2. `source_files`
3. `parse_artifacts`
4. `rule_results`
5. `manual_decisions`
6. `review_revisions`
7. `stage_failures`

Minimum constraints:

- Primary keys are durable IDs; task-owned rows have foreign keys to `tasks` with an intentional delete policy.
- A task stores its exact `TaskState`, active revision number, created/updated UTC timestamps, and enough display metadata for later API use.
- Source-file storage covers the Task 2 `StagedFile` identity/facts without storing file bytes as BLOBs.
- Rule results preserve system initial status and diagnostics/evidence as serialized JSON text, plus frozen engine version and active revision number.
- Manual decisions preserve the system result link, final status, nonblank reason, optional supplemental evidence, actor, and decision time.
- Review revisions preserve an immutable result snapshot, completion time, task ID, and revision number.
- Stage failures preserve stage, stable code, message, and occurrence time.
- Enforce uniqueness for `(task_id, rule_id, active_revision_no)` on `rule_results` and `(task_id, revision_no)` on `review_revisions`.
- Use closed enum validation at the domain boundary. Database values must round-trip exactly; do not introduce aliases.

If a supporting domain model does not yet exist, add the smallest immutable validated Pydantic model needed for persistence and export it. Avoid speculative fields unrelated to this task.

## Required repository behavior

Produce a closeable repository bundle/factory exposing at least:

- `SqliteTaskRepository`: `create`, `get`, `update` matching the typed Task 1 protocol.
- `SqliteResultRepository`: atomic `replace_all(task_id, results)` and `list_for_task(task_id)`; replacement is all-or-nothing and ordered deterministically.
- `SqliteRevisionRepository`: `complete(task_id, decisions)` creates the next unique revision and freezes a full serialized result/decision snapshot; `update_snapshot` for a completed revision raises stable `CompletedRevisionError` and never mutates it.
- A public construction path such as `repositories(database_url)` returning repositories that share an engine and can be closed, then reopened against the same file.

Define stable not-found/conflict exceptions where needed. Never leak partially committed replacements or revisions after a failed operation.

## Required tests

Start with missing-persistence RED. Then cover at least:

1. Apply `alembic upgrade head` to a new temporary SQLite file and assert the seven application tables plus `alembic_version`; prove repository code did not create the schema itself.
2. Assert `PRAGMA foreign_keys` is `1` on independent connections and an invalid foreign-key insert fails.
3. Create a task, replace exactly 21 distinct rule results, close all repositories/engine, reopen, and assert state/results survive with complete field round trips and deterministic order.
4. A failed `replace_all` leaves the previous complete result set unchanged.
5. Duplicate `(task_id, rule_id, active_revision_no)` is rejected by the database constraint.
6. Completing a revision creates revision 1 with a frozen snapshot; a second valid completion creates revision 2; duplicate revision identity is rejected; `update_snapshot` raises `CompletedRevisionError` and the stored snapshot remains byte/semantic equivalent.
7. JSON snapshot serialization is deterministic and uses TEXT columns, with no SQLite JSON query dependency.
8. UTC timestamps round-trip as timezone-aware UTC values at the domain boundary.
9. Task/domain assignment and `model_copy(update=...)` still enforce invariants.
10. Full backend suite remains green.

Migration command from `backend/` must work with a task-local database:

```powershell
$env:HW_REVIEW_DATABASE_URL='sqlite:///./.tmp/migration-check.db'
& 'C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m alembic -c alembic.ini upgrade head
```

Use fresh paths and repository-local pytest `--basetemp` because the host-global pytest temp root may be unreadable.

## Report

`task-3-report.md` must record:

- actual RED command and exact failures;
- migration command, exit code, migration version, and table inventory;
- focused and full-suite GREEN commands/pass counts;
- restart proof, foreign-key proof, atomicity proof, revision immutability proof;
- exact files created/modified and all deviations/risks;
- no Git commit due user constraint.

## Completion gate

Do not claim completion until migration succeeds against a fresh database, focused integration tests pass, full backend tests pass, and the report contains the evidence above.
