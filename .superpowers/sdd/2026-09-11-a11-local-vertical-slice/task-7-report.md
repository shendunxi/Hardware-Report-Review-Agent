# Task 7 — orchestration, lifecycle, persistence extensions, and FastAPI

## Scope and boundary

- Implemented the seven same-origin `/api/tasks` endpoints, SQLite-backed task lifecycle, source manifests, stage diagnostics, manual decisions, completion snapshots, reopen copies, and static mounting after API routes.
- The application factory constructs adapters but never creates or migrates schema. Migration ownership remains `backend/migrations/versions/0001_initial.py`.
- No Git command and no real sample/DOC input was used during Task 7. A post-Task-9 final spec review registered the already verified PDF and DOC adapters beside XLS and added an API-level PDF regression test. Real DOC conversion remains **NO-GO** on this host and returns the genuine-Word diagnostic rather than treating WPS as Word evidence.

## TDD evidence

| Cycle | RED | GREEN |
|---|---|---|
| API package/create upload/static precedence | `ModuleNotFoundError: hw_review.api` (3 focused tests) | 3 passed |
| Validation envelope | framework response had no `error` key (1 focused test) | 1 passed |
| Review: malformed manifest/staging/list | JSON decoder escape; corrupt XLS returned 500; list dropped manifests (3 focused tests) | 3 passed |
| Review: duplicate primary | two primary parts were accepted (1 focused test) | 1 passed |
| Review: exact result set and durable failure | invalid/duplicate/missing A11 IDs or commit conflicts could leave execution unresolved | invalid sets and commit conflicts produce durable `FAILED` diagnostics |

The focused suite was run with the bundled runtime because `python` is not on `PATH`:

```powershell
& 'C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest --basetemp .pytest-tmp\task7-green2 tests/integration/test_task_api.py tests/integration/test_lifecycle.py -q
```

Final focused command:

```powershell
& 'C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest --basetemp .pytest-tmp\task7-rereview-focused tests/integration/test_task_api.py tests/integration/test_lifecycle.py tests/integration/test_sqlite_repository.py -q
```

Result: `45 passed`. FastAPI/Alembic emitted only deprecation warnings.

## Verification

| Check | Result |
|---|---|
| Existing full backend suite | `274 passed, 4 skipped` |
| Compile | `python -m compileall -q src` passed |
| Fresh migration | `alembic upgrade head` completed against a temporary SQLite database |
| Metadata agreement | `alembic check`: `No new upgrade operations detected.` |
| API/static ordering | `/api/tasks/not-a-uuid` produces the API error envelope before the root static mount |
| Ingress cleanup | synthetic XLS creation asserts no `*/ingress/*` residue |
| Durable execution claim | two concurrent claim attempts produced exactly one owner and durable `FILES_STAGED` state |
| Concurrent HTTP execution | two concurrent `POST /execute` requests returned 202 while the evaluator ran exactly once |
| Failure/cleanup diagnostics | injected parser + cleanup failures produced `FAILED`, no active results, and both persisted diagnostics |
| Result-set boundary | missing, duplicate, TR-05, and unknown rule IDs are rejected before the evaluation transaction can mutate facts |
| Result-set failure state | evaluator validation failures and repository commit conflicts produce durable `FAILED` diagnostics and no active results |
| Transaction rollback | injected mid-transaction SQL failures for evaluation, failure, completion, and reopen preserve all prior state/facts |
| Restart/two revisions | task/source/results/decision/failure/revision reads survive restart; first and second snapshots stay immutable with revision numbers 1 and 2 |

## Endpoint/state/error inventory

| Endpoint | State/result |
|---|---|
| `POST /api/tasks` | validates multipart input, persists a `CREATED` task/source manifests, stages generated copies, removes ingress |
| `POST /api/tasks/{id}/execute` | returns 202 and schedules ordered `CREATED → FILES_STAGED → PARSING → PARSED → EVALUATING → READY_FOR_REVIEW`; records `FAILED` diagnostics on failure |
| `GET /api/tasks`, `GET /api/tasks/{id}` | deterministic task list/detail with manifests, diagnostics, active results/decisions, revisions |
| `PUT .../manual-decision` | READY-only, fixed `local-review` actor, durable replacement, rejects inactive rules/status/reason/state |
| `POST .../complete` | READY-only pending gate; atomically snapshots/freeze decisions/results and marks complete before cleanup |
| `POST .../reopen` | COMPLETED-only; copies frozen system results to a new active revision and preserves snapshots |

Errors use `{"error":{"code","message","details"}}`; validation errors are normalized to `INVALID_UPLOAD`, `INVALID_STATUS`, or `INVALID_REASON`. Business failures include `TASK_NOT_FOUND`, `INVALID_TASK_ID`, `INVALID_RULE`, `INVALID_TASK_STATE`, `UNRESOLVED_REVIEW_ITEMS`, and `STAGE_FAILURE`.

## Files and deviation record

- Added: API package/routes/application/error mapper, evaluation/lifecycle services, focused integration tests, and this report.
- Extended: domain stage-failure model/export and SQLite repository adapters for source files, failures, task/revision listing, and lifecycle transaction helpers.
- Extended migration `0001`/metadata with the nullable execution-claim fact used by the atomic `CREATED -> FILES_STAGED` compare-and-swap. Fresh migration and metadata agreement remain green.
- The test harness uses a dependency-free ASGI helper because the bundled environment lacks `httpx`; this avoids changing project dependencies.

## Independent-review corrections

- Malformed `supporting_manifest` JSON, duplicate primary parts, support alignment/tag errors, and all staging failures now return stable 422 `INVALID_UPLOAD` envelopes; the internal staging code is retained in `details.stage_code`.
- `GET /api/tasks` now projects persisted manifests, diagnostics, active results/decisions, and revisions for each durable task.
- The state transition used as the background-worker claim is atomic and durable. Only its owner schedules execution; later requests observe the claimed/terminal state and do not schedule a duplicate worker.
- Cleanup failures are no longer swallowed: they add a durable `CLEANUP/CLEANUP_FAILURE` stage diagnostic after a correct failure or completion transaction.
