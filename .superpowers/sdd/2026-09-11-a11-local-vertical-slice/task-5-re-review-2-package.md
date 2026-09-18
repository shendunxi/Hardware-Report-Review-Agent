# Task 5 Scoped Re-review Package — fix round 2/5

Review only the remaining end-to-end child failure-envelope finding and whether its fix introduces a new Critical or Important issue. Do not edit files, spawn subagents, or retry real DOC/WPS.

Claimed fix: on nonzero child exit, the parent strictly parses a valid structured failure envelope first, preserves its stable code/message and bounded child cleanup diagnostics, budgets parent termination/cleanup diagnostics next, and appends only the bounded remaining stderr tail. Malformed failure envelopes map to stable `DOC_CONVERSION_FAILED` with `Word worker returned invalid failure envelope`. A long-stderr regression proves unique primary and cleanup sentinels survive end to end.

Claimed evidence: review-fix RED had 2 intended failures; targeted GREEN 4 passed; final focused 48 passed / 4 skipped; full backend 160 passed / 4 skipped; compileall pass; no real DOC retry or process/temp remnants.

Inspect:

- `backend/src/hw_review/parsers/word_worker.py`
- `backend/tests/integration/test_doc_parser.py`
- `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-5-report.md`

Return `ADDRESSED` or `OPEN` with exact evidence, any new Critical/Important issue, and all verdicts:

- `Implementation spec compliance: PASS|FAIL`
- `Implementation quality: PASS|FAIL`
- `Real PDF acceptance: PASS|FAIL`
- `Real DOC acceptance: NO-GO|PASS`
