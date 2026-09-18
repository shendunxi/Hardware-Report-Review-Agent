# Task 6 Scoped Re-review — fix round 1/5

Review only the four prior findings and new Critical/Important regressions. Do not edit files or spawn subagents.

Claims: TR-10 now uses traceable supplied `必填数据清单`; TR-11 uses supplied `数值字段清单` and flags a declared nonempty value containing no decimal as `NUMERIC_FORMAT_INVALID`; TR-20 handles `非PP`/`非 PP`/`non-pp`/`not pp` before positive PP; TR-03 with neither explicit no-FAIL proof nor FAIL evidence is NON_COMPLIANT with missing material. No field/unit/business criteria are invented.

Inspect `backend/src/hw_review/rules/a11_engine.py`, `backend/tests/unit/test_a11_rules.py`, and `task-6-report.md`. Claimed results: focused 87 passed; full 247 passed/4 known skips; compileall pass.

For each finding return ADDRESSED/OPEN with lines, any new Critical/Important, then `Spec compliance: PASS|FAIL` and `Task quality: PASS|FAIL`.
