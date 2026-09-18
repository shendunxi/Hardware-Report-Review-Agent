# Task 1 independent review package

Review the complete Task 1 implementation. This workspace intentionally has no Git repository; inspect complete files rather than a commit diff.

## Requirements and report

- `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-1-brief.md`
- `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-1-report.md`
- `docs/superpowers/specs/2026-09-11-a11-local-vertical-slice-design.md`

## Complete implementation surface

- `backend/pyproject.toml`
- `backend/src/hw_review/__init__.py`
- `backend/src/hw_review/config.py`
- `backend/src/hw_review/domain/__init__.py`
- `backend/src/hw_review/domain/enums.py`
- `backend/src/hw_review/domain/models.py`
- `backend/src/hw_review/domain/ports.py`
- `backend/tests/unit/test_domain_contracts.py`

## Binding constraints

- No Git use or repository initialization.
- Python 3.12; exact closed status and evidence-kind vocabularies from the brief.
- Supporting files require evidence kinds; primary reports reject them.
- No parser, persistence, rules, API, LLM, OCR, formal XLS writer, authentication or template backend behavior in this task.
- New behavior must have observed RED before production implementation.

## Review duties

1. Verify every brief requirement is implemented without extra vocabulary or scope.
2. Verify Pydantic validation cannot be bypassed by ordinary construction and protocol signatures are usable by later tasks.
3. Evaluate test quality for exact values, invalid combinations, bbox cardinality, nonblank basis fields and runtime-checkable protocols.
4. Verify `pyproject.toml` declares the plan-required runtime dependencies and a working pytest entry point.
5. Use the report's existing test evidence; rerun only if a concrete discrepancy requires it.
6. Report Critical, Important and Minor findings with exact file:line evidence. Give separate `Spec compliance` and `Task quality` verdicts.
7. Do not edit files, use Git or spawn subagents.
