# Task 1 scoped re-review package

Re-review only the findings from Task 1 review round 1. This workspace has no Git; inspect complete current files.

## Inputs

- `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-1-brief.md`
- `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-1-report.md`
- `backend/src/hw_review/domain/enums.py`
- `backend/src/hw_review/domain/models.py`
- `backend/src/hw_review/domain/ports.py`
- `backend/tests/unit/test_domain_contracts.py`

## Findings to verdict

1. Protocols formerly used `object`; confirm they are now usable typed generic contracts, contain no `object` or `Any`, cover all methods, and can be specialized by later Pydantic task/document/result/revision models.
2. Domain model invariants were bypassable through assignment and `model_copy(update=...)`; confirm ordinary public mutation is blocked and public update-copy revalidates the full payload.
3. Closed-vocabulary tests formerly missed aliases and FileRole; confirm exact enum member names are asserted.
4. Bbox tests formerly covered only one invalid length; confirm four values pass and both shorter and longer tuples fail.

Use the report's 19/19 evidence unless code contradicts it. Report each finding as ADDRESSED or NOT ADDRESSED, flag only new Critical/ introduced by this fix, and return separate spec/quality verdicts. Do not edit files, use Git or spawn subagents.
