# Task 7 independent review package

## Review objective

Determine whether Task 7 is safe to accept. Review the implementation and tests; do not edit files.

## Frozen requirements to verify

1. Exactly seven `/api/tasks` endpoints: create, execute, list, detail, manual decision, complete, reopen.
2. Create accepts one primary report plus zero or more supporting files and an aligned JSON evidence-kind manifest; unsafe or invalid input uses the frozen error envelope.
3. Execute is `202`, idempotent under repeated/concurrent requests, and performs the ordered lifecycle `CREATED -> FILES_STAGED -> PARSING -> PARSED -> EVALUATING -> READY_FOR_REVIEW`.
4. The 21 active A11 results and `READY_FOR_REVIEW` state commit atomically. A stage failure commits `FAILED` plus diagnostics atomically, leaves no partial active results, and cleans temporary input.
5. Manual decisions are READY-only, reject disabled/unknown rules and invalid final states, use a server-owned actor, require a reason when overriding, and survive restart.
6. Complete is READY-only, blocks while any effective item is `NEEDS_REVIEW`, atomically freezes the active results/decisions into a revision and marks `COMPLETED`, then cleans staged files.
7. Reopen is COMPLETED-only, increments the active revision, copies frozen system results into a new active revision, returns to READY, and preserves older frozen snapshots.
8. List/detail expose durable source manifests, failures, active results/decisions, and revisions without trusting a client-provided actor.
9. API routes take precedence over a same-origin static mount; no wildcard CORS. App startup must not create or migrate schema.
10. SQLite is the development database only. The real DOC gate remains NO-GO; no WPS-as-Word claim.

## Files in scope

- `backend/src/hw_review/api/app.py`
- `backend/src/hw_review/api/errors.py`
- `backend/src/hw_review/api/routes/tasks.py`
- `backend/src/hw_review/services/evaluation.py`
- `backend/src/hw_review/services/lifecycle.py`
- `backend/src/hw_review/persistence/repositories.py`
- `backend/src/hw_review/persistence/tables.py`
- `backend/tests/integration/test_task_api.py`
- `backend/tests/integration/test_lifecycle.py`
- `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-7-report.md`

## Existing evidence

- Implementer reports 4 focused tests, 251 passed/4 skipped full backend, compile success, migration success, and Alembic metadata agreement.
- The low focused-test count is not sufficient evidence for the frozen lifecycle requirements. Inspect source and identify missing executable proof or implementation defects.

## Required review output

- Verdict: PASS or FAIL.
- Findings ordered by severity, each with exact `path:line`, violated requirement, and concrete consequence.
- Separate implementation defects from missing-test evidence.
- If PASS, state why the available tests prove requirements 1-10.
- Keep output concise; do not restate the project history.
