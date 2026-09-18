# Task 2 Scoped Re-review Package — fix round 2/5

Review only the remaining Important issue from round 1 and whether its fix introduces any new Critical or Important issue. Do not edit files and do not spawn subagents.

## Open finding

`ZipFile.testzip()` decompressed every OOXML member while only compressed source bytes were bounded, allowing a small high-expansion archive to consume unbounded resources before parser timeouts.

## Claimed fix

- Configurable positive local defaults: at most 10,000 members; per-member uncompressed bytes at most `max_file_size_bytes`; aggregate uncompressed bytes at most `4 * max_file_size_bytes`; compression ratio at most 100:1.
- Metadata preflight rejects a package exceeding a ceiling with `ARCHIVE_RESOURCE_LIMIT_EXCEEDED` before task-directory creation.
- Unbounded `testzip()` was replaced with bounded chunked reads of every member; CRC, encrypted, and unreadable members receive stable failures.
- Review-fix RED: 10 failed / 31 passed, plus one additional unreadable-member RED. Final Task 2 focused GREEN: 52 passed. Full backend GREEN: 71 passed.

## Files

- `backend/src/hw_review/services/staging.py`
- `backend/tests/unit/test_staging.py`
- `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-2-report.md`

## Required response

Return `ADDRESSED` or `OPEN` for the finding with exact file/line evidence, any new Critical or Important finding, and:

- `Spec compliance: PASS|FAIL`
- `Task quality: PASS|FAIL`
