# Task 5 Scoped Re-review Package — fix round 1/5

Review only the five prior Important implementation findings and whether fixes introduce any new Critical or Important issue. Do not edit files, spawn subagents, or retry real DOC/WPS.

## Prior findings and claimed fixes

1. Process start/timeout was not failure-safe. Start OSError now maps stably; terminator failures fall back to direct kill; every reap is finitely bounded; timeout stays primary with bounded diagnostics; cleanup is in nested finally paths.
2. Stale artifacts could be accepted. Every conversion uses a fresh unpredictable UUID attempt directory and binds manifest paths to it; PDF/HTML/JSON require exact nonzero size and SHA-256. Existing/empty/mismatched artifacts are rejected.
3. Symlink checks happened after resolve. Parent and child now inspect raw existing path components for symlink plus Windows junction/reparse behavior, then separately enforce resolved containment.
4. COM cleanup diagnostics were lost and uninitialize could override the primary. A child failure envelope now retains the primary conversion failure and bounded Close/restore/Quit/CoUninitialize diagnostics; uninitialize is independently guarded.
5. DOC visual-copy repeated images reused only the first bbox. Xrefs are de-duplicated, then all occurrence rects are expanded once in deterministic order.

Claimed final evidence: Task 5 focused 46 passed / 4 skipped (two honest symlink-privilege skips, two real-DOC Word NO-GO skips); full backend 158 passed / 4 skipped; compileall pass. Real S-07 still passes with unchanged fingerprint. No new real DOC attempt; no worker/WINWORD remnant; unrelated WPS PID untouched.

## Inspect

- `backend/src/hw_review/parsers/word_worker.py`
- `backend/src/hw_review/parsers/doc.py`
- `backend/src/hw_review/domain/models.py`
- `backend/tests/integration/test_doc_parser.py`
- `backend/tests/integration/test_pdf_parser.py`
- `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-5-report.md`

## Required response

For each prior finding return `ADDRESSED` or `OPEN` with exact file/line evidence. Report any new Critical or Important issue. Then return:

- `Implementation spec compliance: PASS|FAIL`
- `Implementation quality: PASS|FAIL`
- `Real PDF acceptance: PASS|FAIL`
- `Real DOC acceptance: NO-GO|PASS`
