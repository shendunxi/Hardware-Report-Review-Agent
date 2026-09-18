# Task 8 implementation brief — real API frontend

## Goal

Connect the approved A11 prototype to the Task 7 same-origin API while preserving the existing approved information architecture, labels, colors, accessibility behavior, and explicit simulation boundaries.

## Files

- Create `prototype/a11-ui/api-client.js`.
- Modify `prototype/a11-ui/index.html`, `app.js`, `styles.css`, `README.md`, and `tests/prototype.test.js`.
- Create `backend/tests/integration/test_static_frontend.py`.
- Create `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-8-report.md`.

## Frozen behavior

1. Default `/` mode is real same-origin API mode. Preserve the current static data only under explicit `?mode=demo`; visible UI must identify demo mode.
2. `api-client.js` loads before `app.js` and exposes `createTask`, `executeTask`, `listTasks`, `getTask`, `saveManualDecision`, `completeTask`, and `reopenTask`.
3. Real mode must never fabricate task IDs, lifecycle states, counts, rule results, evidence, failures, decisions, or revisions. These come from API responses.
4. Upload exactly one primary report plus zero or more supporting files. Each supporting file requires one or more exact `EvidenceKind` selections; send aligned JSON `supporting_manifest` in `FormData`.
5. Before submission, show every selected file's display name, format, role, and selected evidence kinds.
6. After execute, poll only in `FILES_STAGED`, `PARSING`, `PARSED`, or `EVALUATING`; interval is 2 seconds and must stop on navigation, READY, FAILED, COMPLETED, disposal, or a newer task selection.
7. Render stable failure filename/stage/reason and one retry action invoking execute. Never translate a failure into a compliant result.
8. Render the 21 active rule results; TR-05 remains a non-executed source row and never gets a result card or manual-decision form.
9. Preserve separate system initial status/evidence and human final status/reason. Final choices are only `COMPLIANT`, `NON_COMPLIANT`, `NOT_APPLICABLE`; `NEEDS_REVIEW` is system-only.
10. Any manual override requires a nonblank reason; supplemental evidence remains optional. The server response is authoritative.
11. Completion remains blocked by unresolved `NEEDS_REVIEW`; complete/reopen/revision displays come from the API.
12. Render evidence locators by format: XLS sheet/cell, DOC page/paragraph/table, PDF page/area. Do not invent unavailable locator fields.
13. Template management remains visibly simulated. The role selector remains labelled as a permission demonstration, not authentication/authorization.
14. Preserve renamed role labels `测试报告审核` and `模板规则管理`; do not introduce `普通测试人员`, `模板规则管理员`, `无法判断`, `接受例外`, `严重性`, or `A111` into product UI.
15. No CORS workaround and no frontend-side file parsing or result computation.

## TDD and verification

Write failing Node/static-serving tests first. Tests must prove script order, explicit demo mode, no fabricated real-mode identifiers/data, supporting evidence-kind enforcement and manifest alignment, bounded polling and cancellation, failure/retry rendering, API-derived states/counts/results, TR-05 exclusion, manual-decision payload, completion gate, and real static serving.

Run from `prototype/a11-ui`:

- `node --check app.js`
- `node --check api-client.js`
- `node --test tests/prototype.test.js`

Run from `backend` with the bundled Python runtime:

- `python -m pytest tests/integration/test_static_frontend.py -v`
- full backend test suite after focused tests

Perform browser smoke only after Task 7 independently passes. Use a synthetic XLS, not the supplied real samples. Exercise upload -> execute -> 21 results -> evidence -> override -> resolve pending -> complete -> reopen, then inspect 1440x900, 1280x720, and 760x900. Record actual commands, counts, screenshots/observations, limitations, and any NO-GO in the Task 8 report. Do not use Git.
