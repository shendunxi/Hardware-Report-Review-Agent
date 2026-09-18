# Task 4 Scoped Re-review Package — fix round 1/5

Review only the four prior Important findings and whether fixes introduce any new Critical or Important issue. Do not edit files and do not spawn subagents.

## Prior findings and claimed fixes

1. Evidence identity could drift. Shared non-circular hash helpers now validate cell display/hash, table/text block hashes, document digest, and exact sheet locator prefixes during construction and `model_copy`; workbook-level object locators remain explicitly allowed.
2. Out-of-range XLS dates leaked `OverflowError`. A real xlwt fixture with numeric 4000000 plus date format now preserves raw/deterministic display and emits cell-addressed `DATE_VALUE_OUT_OF_RANGE`.
3. Unknown OLE streams were silently skipped. Every non-core workbook/property stream is now inventoried deterministically as opaque attachment unless safely classified as image.
4. S-01 cleanup was only success-safe. Outer/nested cleanup guards and injected staging/parser/fingerprint/assertion failures now prove the UUID directory is removed while the source stays unchanged.

Claimed final results: Task 4 22 passed; full backend 112 passed; compileall pass. S-01: 18 sheets, 6,358 cells, 82 non-core OLE streams, about 0.49 seconds, unchanged source fingerprint, zero temporary remnants.

## Inspect

- `backend/src/hw_review/domain/hashing.py`
- `backend/src/hw_review/domain/models.py`
- `backend/src/hw_review/parsers/base.py`
- `backend/src/hw_review/parsers/xls.py`
- `backend/tests/unit/test_parser_contract.py`
- `backend/tests/integration/test_xls_parser.py`
- `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-4-report.md`

## Required response

For each prior finding return `ADDRESSED` or `OPEN` with exact file/line evidence; report new Critical or Important issues; then:

- `Spec compliance: PASS|FAIL`
- `Task quality: PASS|FAIL`
