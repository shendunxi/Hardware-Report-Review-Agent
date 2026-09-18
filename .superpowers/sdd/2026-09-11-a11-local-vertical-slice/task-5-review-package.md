# Task 5 Independent Review Package

Review Task 5 as a direct complete-file review because Git is intentionally unavailable. Do not edit files and do not spawn subagents.

## Requirements

- `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-5-brief.md`
- `docs/superpowers/plans/2026-09-11-a11-local-vertical-slice.md` Task 5
- `docs/superpowers/specs/2026-09-11-a11-local-vertical-slice-design.md` sections 4.2, 5.1, 5.3, 5.4, 9, and 10
- `docs/requirements/a11-validation-sample-catalog-v0.1.md` S-06, S-07, S-14
- ledger ruling that genuine Microsoft Word is absent and real DOC acceptance must remain NO-GO; WPS cannot substitute

## Implementation

- `backend/src/hw_review/parsers/pdf.py`
- `backend/src/hw_review/parsers/doc.py`
- `backend/src/hw_review/parsers/word_worker.py`
- `backend/src/hw_review/parsers/__init__.py`
- `backend/src/hw_review/domain/models.py`
- `backend/src/hw_review/domain/__init__.py`
- `backend/tests/integration/test_pdf_parser.py`
- `backend/tests/integration/test_doc_parser.py`
- `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-5-report.md`

## Claimed evidence

- Focused automated suite: 34 passed, 2 real-DOC NO-GO skips.
- Full backend: 147 passed, 2 skipped. Compileall passed.
- Real S-07 PDF PASS: 55 pages, 627 text blocks, 46 table candidates, 94 images, 1.0883 seconds, 153,096,192-byte peak process memory, unchanged fingerprint, cleanup complete.
- S-06/S-14 fingerprints unchanged and workspaces cleaned, but real conversion is NO-GO because Word COM resolves to WPS 12.8.2.18581 and Microsoft `WINWORD.EXE` is absent.
- No worker-process remnant; an unrelated WPS PID predating the task was deliberately untouched.

## Review priorities

1. PDF parsing is deterministic, source-bound, page/bbox/hash preserving, image/table aware without OCR or semantic claims, and protected/corrupt failures are stable.
2. Only the child execution path imports/owns COM; Word safety flags, close-without-save, quit/uninitialize, link-option restore, and primary-error preservation are correct in all paths.
3. Parent launches with argument list/no shell, bounds diagnostics, validates artifact containment/hash/source identity, handles timeout and kills/reaps only its worker-owned tree.
4. DOC normalization preserves original plus conversion provenance, paragraph/table/page structure, and stable identities without treating intermediates as originals.
5. Real acceptance and cleanup evidence are honest and failure-safe; WPS is not mislabeled as Word; DOC/DOCX compatibility claims remain appropriately limited.
6. Tests can catch traversal, symlink, stale/hash-mismatched artifacts, hanging workers, leaked processes, COM flag regressions, image-only PDFs, and cleanup bypasses.

You may rerun only synthetic/focused tests and inspect current process state. Do not retry real DOC conversion on WPS and do not modify any sample.

## Required response

Return findings ordered Critical, Important, Minor with exact file/line references. Then separately report:

- `Implementation spec compliance: PASS|FAIL`
- `Implementation quality: PASS|FAIL`
- `Real PDF acceptance: PASS|FAIL`
- `Real DOC acceptance: NO-GO|PASS`

If implementation fails, give minimum concrete fixes/tests. An honest environment-based DOC NO-GO is not by itself an implementation defect.
