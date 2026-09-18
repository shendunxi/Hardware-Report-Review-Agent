# Task 7 Brief — orchestration, lifecycle, persistence extensions, and FastAPI

Implement Task 7 from the plan/design: the seven frozen endpoints, persisted stage transitions, idempotent execution, manual review, completion/reopen snapshots, restart recovery, and same-origin static serving.

## Binding scope

- Source: plan Task 7 and design sections 3, 7, 8, 9. Existing Tasks 1–6 are contracts.
- Local single-user only; no login/authorization, LLM, OCR, formal export, template backend, production DB, CORS relaxation, or Git.
- SQLite schema is migration-owned; runtime must not create tables. Modify migration `0001`/metadata only for missing Task-7 facts, then prove fresh migration plus `alembic check`.
- Keep the real DOC gate NO-GO; API must surface stable conversion failures, not call WPS as Word.
- Strict TDD, concise report.

## Files

Create the plan-listed service/API/test/report files: `services/evaluation.py`, `services/lifecycle.py`, `api/errors.py`, `api/__init__.py`, `api/routes/tasks.py`, `api/app.py`, `tests/integration/test_task_api.py`, `tests/integration/test_lifecycle.py`, and `task-7-report.md`.

Modify only the minimum existing config/domain/persistence/parser exports and migration needed for source manifests, stage failures, revision listing, and atomic lifecycle commits. Do not change requirements, design, prototype behavior, parser/rule semantics, or prior tests.

## API contract

Implement exactly:

- `POST /api/tasks` multipart: one `primary_report`; zero or more `supporting_files`; one JSON `supporting_manifest` array aligned by index, each entry containing nonempty `evidence_kinds`. Reject count mismatch, invalid kinds, more than one primary, blank/unsafe names, empty/unsupported/corrupt/oversize inputs. Upload bytes first go to a generated task-local ingress path; user names are metadata only; stage through the existing safety boundary; remove ingress in all paths. Return task ID, manifests, and `CREATED`.
- `POST /api/tasks/{id}/execute`: return 202 and run one local background execution. Repeated/concurrent calls are idempotent; never create duplicate results or workers. Terminal READY/COMPLETED returns the existing task; FAILED requires a new task in this slice.
- `GET /api/tasks`: deterministic recent list from SQLite.
- `GET /api/tasks/{id}`: task, source manifests, stage diagnostics, exactly 21 active results when ready, active decisions/final-state projection, and revision list.
- `PUT /api/tasks/{id}/rules/{rule_id}/manual-decision`: only READY; reject TR-05/unknown, `NEEDS_REVIEW` as final state, blank reason, completed task. Accept `COMPLIANT|NON_COMPLIANT|NOT_APPLICABLE`; supplemental evidence optional. Actor is a fixed server-side local-review identity, not trusted from request input. Save-or-replace durably.
- `POST /api/tasks/{id}/complete`: only READY; every system `NEEDS_REVIEW` must have a manual final decision. Nonpending unmodified results are implicitly accepted. Atomically create immutable revision snapshot, freeze decisions, set `COMPLETED`, then failure-safely clean task files. Cleanup failure is diagnostic and must not undo the durable completion.
- `POST /api/tasks/{id}/reopen`: only COMPLETED; atomically increment active revision, copy the frozen system results into the new active revision with deterministic new IDs, clear active draft decisions, set READY, and preserve all older snapshots. Because completed source files were cleaned, do not silently rerun parsing.

Errors use exactly `{"error":{"code":...,"message":...,"details":{...}}}` with stable 4xx/5xx mapping. Required codes include not found, invalid upload/state/status/reason/rule, unresolved review items, parser/stage failures, and internal execution failure without stack leakage.

`create_app(settings) -> FastAPI` registers API routes first, then serves `prototype/a11-ui` from `/` on the same origin. Default run/bind policy remains `127.0.0.1`; no permissive CORS middleware.

## Orchestration and persistence

- Persist ordered transitions: `CREATED → FILES_STAGED → PARSING → PARSED → EVALUATING → READY_FOR_REVIEW`; invalid jumps fail stably.
- Parse only persisted staged copies using `ParserRegistry`; build `ReviewInput` from all sources and execute A11 exactly once per active revision.
- Do not expose partial conclusions: commit all 21 results plus READY state atomically only after complete evaluation.
- Any stage failure atomically records `FAILED` plus stage/code/message/UTC occurrence, cleans the task directory, and retains no partial active result set.
- Provide repositories for source-file create/list, stage-failure create/list, task list, revision list, and the minimum application/lifecycle transaction boundary. Business services depend on protocols, not SQLite SQL.
- Completion snapshot + task state, evaluation result replacement + READY state, failure record + FAILED state, and reopen copy + new state are each single database transactions. Tests must inject mid-transaction failures and prove rollback.
- UTC only at persistence/domain boundary. App/repository resources and executor shut down cleanly.

## TDD/acceptance

Cover at least:

1. Fresh migration/metadata agreement and no runtime schema creation.
2. Multipart primary-only and primary+support creation; support-tag/count/format/signature/size failures; no path traversal or ingress residue.
3. Synthetic XLS create→execute→poll READY yields 21 ordered results/no TR-05; double/concurrent execute stays 21.
4. Every valid/invalid state transition, parser failure persistence, no partial results, task-dir cleanup.
5. Manual status/reason/rule validation; save→restart→replace persistence.
6. Pending completion rejection with exact `details.remaining`; successful implicit acceptance; immutable snapshot; edit-after-complete rejection.
7. Reopen then second completion yields two independent revisions and old snapshot bytes unchanged.
8. Restart app/repositories against the same migrated SQLite file and read task, 21 results, decisions, failures, revisions.
9. Inject atomic-commit failures for evaluation/failure/completion/reopen and prove no half-state.
10. `/api/*` wins over static mount, `/` serves the prototype, no CORS wildcard, fixed local actor is returned.
11. Focused suite, full backend, compileall, fresh migration/Alembic check, and zero generated task/ingress/temp remnants.

Use a controllable executor or synchronous test hook so tests poll deterministically without weakening production idempotency. Do not open real samples; synthetic XLS is sufficient here.

## Report/gate

Record RED/GREEN commands and counts, endpoint/state/error matrices, idempotency/concurrency/restart/atomicity/cleanup evidence, migration inventory, files/deviations, known DOC NO-GO, and no Git. Task completes only after independent review passes.
