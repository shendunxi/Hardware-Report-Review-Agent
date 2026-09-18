# Task 2 Independent Review Package

## Review scope

Review Task 2 only, as a direct complete-file review because Git is intentionally unavailable. Do not edit files and do not spawn subagents.

## Requirements

- `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-2-brief.md`
- `docs/superpowers/plans/2026-09-11-a11-local-vertical-slice.md` Task 2
- `docs/superpowers/specs/2026-09-11-a11-local-vertical-slice-design.md` sections 4.1, 5.1, and 9
- `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/progress.md`

## Implementation and tests

- `backend/src/hw_review/domain/models.py`
- `backend/src/hw_review/domain/__init__.py`
- `backend/src/hw_review/services/__init__.py`
- `backend/src/hw_review/services/staging.py`
- `backend/src/hw_review/services/cleanup.py`
- `backend/tests/unit/test_staging.py`
- `backend/tests/unit/test_cleanup.py`
- `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-2-report.md`

## Claimed evidence

- Initial RED: collection failed in both Task 2 test modules because services were absent.
- Additional model-invariant RED: 2 failed.
- Focused GREEN: 27 passed.
- Full backend GREEN: 46 passed.
- Real samples were not accessed; all test cleanup was confined to repository-local pytest temp directories.

You may rerun tests with the bundled Python and a fresh `--basetemp` under `backend/.pytest-tmp/` if useful.

## Review questions

1. Does `StagedFile` preserve Task 1 invariants and provide a usable Task 4 parser input?
2. Is format identification actually content-based for PDF, OOXML, and OLE, with stable rejection codes and no source mutation?
3. Can a user-controlled filename, path, symlink, malformed UUID, or unsupported file cause staging or cleanup to escape the configured work root?
4. Does copy failure leave no parser-visible payload?
5. Does expiry cleanup remove only canonical UUID task directories at or beyond the threshold and return deterministic IDs?
6. Do tests prove behavior rather than merely mirror implementation?

## Required response

Return findings ordered Critical, Important, Minor with exact file and line references. Then return separate verdicts:

- `Spec compliance: PASS|FAIL`
- `Task quality: PASS|FAIL`

If either verdict fails, name the minimum concrete fixes and tests required. Ignore formatting-only preferences unless they create a real correctness or maintainability risk.
