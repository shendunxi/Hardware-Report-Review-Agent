# Task 6 Independent Review Package

Review Task 6 directly; Git is unavailable. Do not edit files, spawn subagents, or inspect unrelated tasks.

Requirements: `task-6-brief.md`, `docs/requirements/template-check-rules-v0.1.md`, `docs/requirements/template-field-dictionary-v0.1.md`, and design section 6.

Implementation/tests: `backend/src/hw_review/rules/`, relevant additions in `backend/src/hw_review/domain/`, `backend/tests/unit/test_a11_*.py`, and `task-6-report.md`.

Claims: exact 22 source definitions/21 executed; TR-05 disabled; deterministic IDs/query/rollup; no LLM or invented criteria; AI-only rules do not rule-only pass. Focused 78 passed; full 238 passed/4 known environment skips; compileall passed.

Review priorities:

1. Every registry field and order matches the frozen table exactly; no invented criterion, severity, URL pattern, applicability, or evidence location.
2. `NOT_APPLICABLE` requires proof; required missing evidence/objective failure outranks semantic pending; compliant is positive proof only; TR-05 never emits a result.
3. All 21 rules implement the specified missing/objective/N-A/pending/compliant boundaries conservatively, especially TR-07/08/09/16/22 missing published criteria and AI-only TR-13/16/17/18.
4. Query results are source-bound, deterministic, literal, traceable, and evidence-kind routing never infers from filenames.
5. Every noncompliant has evidence or missing materials; every pending has unresolved semantics; result IDs/version/timestamps are coherent and repeatable.

Return findings ordered Critical/Important/Minor with exact lines, then `Spec compliance: PASS|FAIL` and `Task quality: PASS|FAIL`. If failed, state minimum fixes/tests.
