# Task 2 Scoped Re-review Package — fix round 1/5

Review only whether the four prior Important findings are addressed and whether the fixes introduce any new Critical or Important defect. Do not edit files and do not spawn subagents.

## Prior findings

1. A malformed or hostile runtime `task_id` could create a directory outside `work_root` before containment validation.
2. A post-copy `StagedFile` construction failure could leave the payload in `input/`; blank `SourceFileCreate.original_name` was accepted.
3. OOXML recognition checked names only and accepted missing content-types manifests or members with invalid CRC.
4. No configurable pre-copy file-size ceiling existed.

## Claimed fixes

- `stage()` now coerces task identity before source or task-specific filesystem work, accepting only `UUID` or canonical lowercase hyphenated UUID text. `_verified_input_dir()` resolves and proves the task path is a direct root child before `mkdir`.
- `SourceFileCreate.original_name` now rejects blank or whitespace-only values. Every exception after destination creation removes the destination before re-raising.
- OOXML requires `[Content_Types].xml` and runs `ZipFile.testzip()` before identifying XLSX/DOCX.
- `FileStager` accepts a positive `max_file_size_bytes`, defaults locally to exactly 100 MiB, rejects larger inputs with `FILE_TOO_LARGE` before task-directory creation or copy, and accepts the exact boundary. This is a development default, not a production policy.
- Review-fix RED: 11 failed / 18 passed. Final focused GREEN: 39 passed. Full backend GREEN: 58 passed.

## Files to inspect

- `backend/src/hw_review/services/staging.py`
- `backend/src/hw_review/domain/models.py`
- `backend/tests/unit/test_staging.py`
- `backend/tests/unit/test_cleanup.py`
- `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-2-report.md`

## Required response

For each of the four prior findings, return `ADDRESSED` or `OPEN` with file/line evidence. Report any new Critical or Important issue. Then provide:

- `Spec compliance: PASS|FAIL`
- `Task quality: PASS|FAIL`
