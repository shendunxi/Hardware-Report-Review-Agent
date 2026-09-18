# Task 3 report — SQLite schema, migrations, and lifecycle repositories

## TDD evidence

### RED

Command, from `backend/`:

```powershell
& 'C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/integration/test_sqlite_repository.py -v --basetemp E:\Coding\Hardware-Report-Review-Agent\backend\.pytest-tmp\task3-red
```

Exit code: `1`. Exact summary: `collected 0 items / 1 error`. Collection stopped with `ImportError: cannot import name 'ManualDecision' from 'hw_review.domain'`. This was the expected missing-persistence failure before the Task 3 domain records, schema, migration, and repositories existed.

The first implementation run then collected all 11 tests and produced `5 failed, 6 passed in 8.05s`. All five failures identified the same incomplete serializer boundary: nested immutable `EvidenceLocator` values in tuples were not JSON serializable. The minimum correction converted the complete input recursively to JSON-compatible primitives before canonical serialization.

A self-review found that the required `TaskRepository.update` path lacked a dedicated behavioral test. The method was removed before adding the test, and the focused RED command produced `1 failed in 1.32s` with `AttributeError: 'SqliteTaskRepository' object has no attribute 'update'`. Restoring the minimum implementation produced `1 passed in 1.19s`; the test proves state, active revision number, and updated UTC time survive engine disposal and reopening.

### GREEN — focused

Final command, from `backend/`:

```powershell
& 'C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/integration/test_sqlite_repository.py -v --basetemp E:\Coding\Hardware-Report-Review-Agent\backend\.pytest-tmp\task3-focused-final-2
```

Exit code: `0`. Exact summary: `12 passed in 7.91s`.

### GREEN — full backend suite

Final command, from `backend/`:

```powershell
& 'C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -v --basetemp E:\Coding\Hardware-Report-Review-Agent\backend\.pytest-tmp\task3-full-final-2
```

Exit code: `0`. Exact summary: `84 passed in 8.42s`.

Final completion-gate rerun combined a fresh `0001` migration, table/version inspection, and `pytest -q`: exit code `0`, the same eight-table inventory, `version=0001`, and `84 passed in 9.39s`. Its task-local database was verified absent after cleanup.

## Migration evidence

The migration was applied to a fresh task-local SQLite database with:

```powershell
$env:HW_REVIEW_DATABASE_URL='sqlite:///./.tmp/migration-check-task3-final.db'
& 'C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m alembic -c alembic.ini upgrade head
```

Exit code: `0`. Alembic reported `Running upgrade  -> 0001, Create the initial local-review persistence schema.` The recorded migration version was `0001`.

The resulting table inventory was:

- `alembic_version`
- `manual_decisions`
- `parse_artifacts`
- `review_revisions`
- `rule_results`
- `source_files`
- `stage_failures`
- `tasks`

`python -m alembic -c alembic.ini check` against this database returned exit code `0` and `No new upgrade operations detected`, proving the migration and SQLAlchemy metadata agree. The task-local migration-check database was removed after this evidence was recorded.

## Behavioral proofs

- **Runtime schema boundary:** constructing a repository bundle against an unmigrated new file leaves the table inventory empty; the first task lookup fails with SQLite `OperationalError`. No repository constructor calls `create_all` or synthesizes schema.
- **Foreign keys:** every application engine connection installs `PRAGMA foreign_keys=ON`; two independent checked-out connections each returned `1`, and a `rule_results` insert for a nonexistent task failed with `IntegrityError`. The Alembic online engine uses the same pragma installer.
- **Restart durability:** a task and 21 complete `RuleResult` records were written, the shared engine was disposed, a new bundle opened the same file, and equality checks passed for task state, timestamps, every result field, nested evidence, missing-material diagnostics, unresolved-semantic diagnostics, and rule order. A separate create/update/reopen path verified all required task repository operations.
- **Atomic replacement:** a replacement containing duplicate `(task_id, rule_id, active_revision_no)` identities raised stable `RepositoryConflictError`; after rollback, all 21 prior results remained byte/semantic equivalent at the domain boundary.
- **Database uniqueness:** an independent direct insert with a duplicate task/rule/revision identity failed with `IntegrityError` under the named database unique constraint.
- **Revision immutability:** valid completions created unique revisions 1 and 2 with canonical full result/decision snapshots. `update_snapshot` raised stable `CompletedRevisionError`; rereading revision 1 returned the original snapshot unchanged. An independent duplicate `(task_id, revision_no)` insert failed with `IntegrityError`. Both revisions survived engine disposal and reopening.
- **Deterministic TEXT JSON:** evidence, diagnostics, supplemental evidence, and complete revision snapshots use SQL `TEXT`; serialization uses UTF-8-safe canonical JSON with sorted keys and compact separators. No repository query uses SQLite JSON functions.
- **UTC:** aware input datetimes are normalized to UTC before storage and reconstructed as timezone-aware UTC values. Naive datetimes are rejected by immutable Pydantic domain models.
- **Domain integrity:** `ReviewTask`, `RuleResult`, `ManualDecision`, and `ReviewRevision` are immutable. Assignment and `model_copy(update=...)` revalidate closed enums, nonblank fields, nonnegative revision values, and aware timestamps.

## Files created or modified

Created:

- `backend/alembic.ini`
- `backend/migrations/env.py`
- `backend/migrations/versions/0001_initial.py`
- `backend/src/hw_review/persistence/__init__.py`
- `backend/src/hw_review/persistence/database.py`
- `backend/src/hw_review/persistence/tables.py`
- `backend/src/hw_review/persistence/repositories.py`
- `backend/tests/integration/test_sqlite_repository.py`
- `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-3-report.md`

Modified only to add/export the smallest persistence domain records:

- `backend/src/hw_review/domain/models.py`
- `backend/src/hw_review/domain/__init__.py`

`backend/migrations/script.py.mako` was not created because this task applies a hand-authored fixed migration and does not generate revisions. `backend/pyproject.toml`, Task 1/2 tests, staging/cleanup services, requirements, design, plan, prototype, and real samples were not modified.

## Deviations and remaining risks

- No production database is selected or encoded. This adapter is named and exercised as SQLite-only local development persistence.
- Task 3 stores source-file and parse-artifact facts in schema but intentionally does not add repositories for them; later parser/orchestration tasks may add repository APIs without changing the initial table set.
- The database stores structured content as deterministic JSON text and validates closed status vocabularies with SQL check constraints, but application-level JSON shape validation remains at the repository/domain boundary rather than inside SQLite.
- Revision-number allocation is transaction-scoped and backed by a unique constraint. A concurrent conflicting completion returns stable `RepositoryConflictError`; automatic retry policy belongs to later orchestration rather than this persistence task.
- No real report sample was accessed. All generated databases and pytest data remained under repository-local temporary directories.
- No Git command or commit was used, by user constraint.

## Independent-review fix round 1/5

Three Important findings were verified against the implementation: active manual decisions had no persistence API before completion, non-empty result replacement did not bind its revision number to the task's active revision, and completion accepted duplicate decisions for one system result.

### Review-fix RED

The first regression command selected the active-decision lifecycle, stale/future result replacement, and duplicate completion cases:

```powershell
& 'C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/integration/test_sqlite_repository.py::test_active_decision_survives_restart_can_be_replaced_then_is_frozen tests/integration/test_sqlite_repository.py::test_replace_all_rejects_stale_and_future_revisions_without_data_loss tests/integration/test_sqlite_repository.py::test_duplicate_completion_decisions_roll_back_revision_and_association -v --basetemp E:\Coding\Hardware-Report-Review-Agent\backend\.pytest-tmp\task3-fix1-red
```

Exit code: `1`. Exact summary: `4 failed in 4.62s`. The failures were one missing `RepositoryBundle.decisions`, two `DID NOT RAISE RepositoryConflictError` cases for stale/future revisions, and a second missing decision repository at duplicate-completion setup.

The direct database-constraint test was run with both new decision unique constraints intentionally absent. It failed as expected with `DID NOT RAISE IntegrityError`; exact summary: `1 failed in 1.36s`. Restoring both constraints produced `1 passed in 1.41s`.

The domain-port test initially failed with `ImportError: cannot import name 'DecisionRepository' from 'hw_review.domain'`; exact summary: `1 failed in 2.14s`. Adding the bounded runtime-checkable protocol and export produced `1 passed in 1.64s`.

### Remediation

1. Added `SqliteDecisionRepository` as `RepositoryBundle.decisions`, with `save_or_replace(task_id, decision)` and active-revision `list_for_task(task_id)`. Added a bounded runtime-checkable `DecisionRepository` domain port so later business services need not depend on SQLite classes.
2. Active decisions now store `task_id` and `active_revision_no`; `revision_id` remains null while editable. One decision is permitted for each `(task_id, rule_result_id, active_revision_no)`. Saving an active decision replaces the authoritative row, survives engine disposal/reopening, and rejects any edit after revision association with `CompletedRevisionError`.
3. Completion rejects duplicate `rule_result_id` values before opening its revision write path. In one transaction it applies any passed replacements, rereads the authoritative active-decision set, freezes that exact set into canonical snapshot JSON, inserts the revision, and associates all active decisions with it. The database separately enforces one decision per `(revision_id, rule_result_id)`. Integrity failures map to stable `RepositoryConflictError` and roll back decision changes, revision creation, and association together.
4. `replace_all` now reads the task's active revision inside the same write transaction before deletion or insertion. Every non-empty result must match that exact revision; stale and future values raise `RepositoryConflictError`. Empty replacement still deletes only the task's actual active-revision rows.
5. Updated the hand-authored `0001` migration and SQLAlchemy metadata together. Runtime schema creation remains absent.

### Migration proof after fixes

A fresh migration used `HW_REVIEW_DATABASE_URL=sqlite:///./.tmp/migration-check-task3-fix1.db` and returned exit code `0`, version `0001`, and the unchanged required inventory of seven application tables plus `alembic_version`.

`manual_decisions` reported these persistence facts:

- `task_id` non-null
- `rule_result_id` non-null
- `revision_id` nullable while active
- `active_revision_no` non-null
- `uq_manual_decisions_task_result_active_revision`
- `uq_manual_decisions_completed_revision_result`

`python -m alembic -c alembic.ini check` returned exit code `0` with `No new upgrade operations detected`.

### Final GREEN after fix round 1

Focused command:

```powershell
& 'C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/integration/test_sqlite_repository.py -v --basetemp E:\Coding\Hardware-Report-Review-Agent\backend\.pytest-tmp\task3-fix1-focused-final
```

Exact summary: `18 passed in 18.34s`.

Full backend command:

```powershell
& 'C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -v --basetemp E:\Coding\Hardware-Report-Review-Agent\backend\.pytest-tmp\task3-fix1-full-final
```

Exact summary: `90 passed in 15.50s`.

The final post-report verification command used a new repository-local basetemp and returned `90 passed in 15.23s` with exit code `0`.

### Files changed in fix round 1

- Modified `backend/migrations/versions/0001_initial.py`.
- Modified `backend/src/hw_review/domain/ports.py` and `backend/src/hw_review/domain/__init__.py`.
- Modified `backend/src/hw_review/persistence/tables.py`, `repositories.py`, and `__init__.py`.
- Modified `backend/tests/integration/test_sqlite_repository.py`.
- Appended this evidence to `task-3-report.md`.

No production database choice was introduced, no runtime schema synthesis was added, no real sample was accessed, and no Git command or commit was used.
