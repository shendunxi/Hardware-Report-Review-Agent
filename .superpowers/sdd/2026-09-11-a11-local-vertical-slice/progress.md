# SDD ledger — plan: docs/superpowers/plans/2026-09-11-a11-local-vertical-slice.md

## Preflight rulings

- Ruling: Execute directly in the existing workspace without Git worktrees or commits — the user explicitly said not to configure Git and later authorized recommended continuous execution — cost if wrong: rollback and change-range review depend on complete-file packages rather than commits.
- Ruling: Use fresh implementer and reviewer agents task-by-task — the user authorized all subsequent recommended choices, and the selected implementation plan recommends subagent-driven execution — cost if wrong: higher agent usage than inline execution.
- Ruling: Retain this plan-scoped SDD workspace after completion — without Git history it is the only durable implementation and review audit record — cost if wrong: additional local process artifacts remain in the workspace.
- Ruling: Treat S-06 and S-14 DOC files as the task primaries for paired groups R-06 and R-13, and S-07/S-15 PDF files as compatibility alternates — this reconciles 17 parser inputs with 15 business tasks without duplicating results — cost if wrong: reviewers may prefer PDF rather than DOC as the canonical business representation for those two groups.
- Ruling: Resolve and record the bundled Python absolute path before work; do not assume `python` is on PATH — current dependency discovery returned Python 3.12.14 at `C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe` — cost if wrong: commands may need rerouting to a project virtual environment after dependencies are installed.
- Ruling: Use a configurable 100 MiB local-development source-file ceiling, with OOXML defaults of 10,000 members, one source-file ceiling per member, four source-file ceilings aggregate, and 100:1 compression ratio — the user delegated subsequent recommendations and production limits remain explicitly unfrozen — cost if wrong: local tests or unusually large valid reports require configuration overrides, while production still requires an approved policy.
- Ruling: Continue downstream implementation while holding the real-DOC acceptance gate at NO-GO — read-only runtime evidence contradicts the earlier Word guarantee because the standard Word COM CLSID resolves to Kingsoft WPS and common `WINWORD.EXE` paths are absent; WPS must not be reported as Microsoft Word compatibility — cost if wrong: S-06/S-14 require rerun on a machine with genuine Microsoft Word before DOC support can be released.

## Preflight dependency scan

| Tasks | Producer → consumer | Finding / ruling |
|---|---|---|
| 1 → 2 | Domain file roles, evidence kinds and `SourceFileCreate` → staging metadata | Consistent; Task 2 must not introduce new evidence labels |
| 1 → 3 | Repository protocols and lifecycle enums → SQLite implementations | Consistent; SQLite-specific behavior remains behind interfaces |
| 1 → 4 | Normalized models and parser protocol → parser contract/XLS | Consistent; parser implementation cannot emit review states |
| 2 → 4 | `StagedFile` and fingerprints → XLS parser | Consistent; only staged copies are parsed |
| 4 → 5 | `DocumentParser`/`ReportDocument` → DOC/PDF adapters | Consistent; all adapters preserve one evidence-locator model |
| 4,5 → 6 | Normalized documents/evidence → A11 engine | Consistent; rule engine consumes structures and cannot call format libraries |
| 3,4,5,6 → 7 | Repositories, parsers and engine → orchestration/API | Consistent; Task 7 owns state transitions and atomic replacement |
| 7 → 8 | Seven HTTP contracts → real-mode frontend | Consistent; default same-origin mode is real, explicit demo mode retains prototype regression |
| 1–8 → 9 | All interfaces → frozen-sample harness | Consistent after the 17-input/15-task primary-alternate ruling above |
| Task 1 | Contract tests → enum/model implementation | Internally consistent; dependency installation may be required before RED can run |
| Task 2 | Signature/safety tests → staging/cleanup | Internally consistent; no destructive cleanup may run outside generated task roots |
| Task 3 | Restart/snapshot tests → schema/repositories | Internally consistent; temporary migration database must stay under workspace |
| Task 4 | Synthetic contract plus S-01 proof → XLS adapter | Internally consistent; S-01 validates structure, not business correctness |
| Task 5 | Fake worker RED plus real DOC/PDF proof → adapters | Internally consistent; real Word evidence is required before acceptance claims |
| Task 6 | Registry/priority/rule branch tests → engine | Internally consistent; `NON_COMPLIANT` priority is the binding 2026-09-11 correction |
| Task 7 | API/lifecycle RED → orchestration | Internally consistent; 202 response may use an in-process local worker but must remain idempotent |
| Task 8 | Node/API/browser tests → frontend binding | Internally consistent; template screens remain visibly simulated |
| Task 9 | Manifest/assertions → GO/NO-GO evidence | Internally consistent; any parser failure is diagnosed but still keeps G2 NO-GO |

## Environment preflight

- Bundled runtime: Python 3.12.14.
- Present before project setup: `pydantic`.
- Missing before project setup: `fastapi`, `sqlalchemy`, `alembic`, `xlrd`, `olefile`, `fitz`/PyMuPDF, `win32com`, `psutil`, `pytest`.
- Dependency installation is an expected Task 1 setup action and may require network approval.

## Task status

Task 1: fix round 1/5 (4 addressed, 0 open — typed generic protocols; frozen and revalidated domain models; exact enum alias and `FileRole` coverage; exact `bbox` cardinality coverage; no commits by user constraint).

Task 1: complete (no commits by user constraint; independent scoped re-review clean; focused and full suite 19/19 pass).

Task 2: fix round 1/5 (0 addressed, 4 open — validate canonical UUID task identity before any filesystem mutation; remove every copied payload if any later validation fails; verify OOXML package markers and member integrity; add configurable pre-copy file-size ceiling with stable rejection; no commits by user constraint).

Task 2: fix round 1/5 (4 addressed, 1 new open — prior findings closed; bounded OOXML decompression remains required to prevent a small compressed package bypassing the raw-file ceiling; no commits by user constraint).

Task 2: fix round 2/5 (0 addressed, 1 open — enforce configurable member-count, per-member uncompressed-size, aggregate uncompressed-size, and compression-ratio limits before CRC traversal, then verify members with bounded streaming reads; no commits by user constraint).

Task 2: fix round 2/5 (1 addressed, 1 new open — bounded archive traversal is complete; malformed DEFLATE data still leaks raw `zlib.error` rather than stable `CORRUPT_FILE`; no commits by user constraint).

Task 2: fix round 3/5 (0 addressed, 1 open — map genuine corrupt DEFLATE streams to `CORRUPT_FILE` and prove no task directory is created; no commits by user constraint).

Task 2: fix round 3/5 (1 addressed, 0 open — corrupt DEFLATE streams now map to `CORRUPT_FILE`; independent scoped re-review found no new Critical or Important issue; no commits by user constraint).

Task 2: complete (no commits by user constraint; final focused suite 53/53 pass; full backend suite 72/72 pass; independent review verdicts both PASS).

Task 3: fix round 1/5 (0 addressed, 3 open — persist and replace active-revision manual decisions before completion and across restart; reject result replacement for non-active revisions transactionally; reject duplicate decisions per rule result in code and schema with full rollback; no commits by user constraint).

Task 3: fix round 1/5 (3 addressed, 0 open — active decisions persist and freeze atomically; result replacement is bound to the actual active revision; duplicate decisions are rejected in code and by dual uniqueness constraints; no commits by user constraint).

Task 3: complete (no commits by user constraint; fresh migration and Alembic metadata check pass; focused suite 18/18 pass; full backend suite 90/90 pass; independent review verdicts both PASS).

Task 4: fix round 1/5 (0 addressed, 4 open — make cell/table/document hashes and sheet structural prefixes self-consistent under construction/copy; handle unrenderable XLS dates without raw exceptions; inventory unknown non-core OLE streams as opaque evidence; make S-01 cleanup failure-safe; no commits by user constraint).

Task 4: fix round 1/5 (4 addressed, 0 open — normalized identity self-validates; unrenderable dates produce located warnings; unknown non-core OLE streams remain opaque evidence; S-01 cleanup is failure-safe; no commits by user constraint).

Task 4: complete (no commits by user constraint; S-01 read-only proof passed with 18 sheets, 6,358 nonempty cells, 82 non-core streams, and unchanged fingerprint; focused suite 22/22 pass; full backend suite 112/112 pass; independent review verdicts both PASS).

Task 5: acceptance blocked / implementation fix round 1/5 (0 addressed, 5 open — bound and clean process-start/timeout/termination failures; bind outputs to a unique current attempt with nonzero size/hash proof; reject symlink/junction path chains before resolve; preserve primary COM failure plus bounded cleanup diagnostics; enumerate every reused-image occurrence in DOC visual copies; real PDF PASS; real DOC NO-GO because Microsoft Word is absent; no commits by user constraint).

Task 5: acceptance blocked / implementation fix round 1/5 (4 addressed, 1 open — process safety, fresh artifacts, reparse-point checks, and image occurrences are closed; nonzero child exit must parse the failure envelope before appending bounded stderr so the primary error and cleanup diagnostics survive end to end; real PDF PASS; real DOC NO-GO; no commits by user constraint).

Task 5: acceptance blocked / implementation fix round 2/5 (0 addressed, 1 open — preserve structured child failure message and diagnostics through `WordWorker.convert()` on nonzero exit; no commits by user constraint).

Task 5: acceptance blocked / implementation fix round 2/5 (1 addressed, 0 open — structured child failures now preserve primary error and bounded cleanup diagnostics end to end; no new Critical or Important issue; no commits by user constraint).

Task 5: implementation complete (no commits by user constraint; focused suite 48 pass / 4 honest skips; full backend suite 160 pass / 4 skips; implementation review verdicts both PASS; real PDF acceptance PASS; real DOC acceptance remains NO-GO because genuine Microsoft Word is unavailable).

Task 6: fix round 1/5 (0 addressed, 4 open — add supplied-checklist-driven TR-10 blank-required-data failure; add supplied numeric-field-list-driven TR-11 invalid numeric-format failure; treat explicit negated/non-PP stages before PP matching; make absent TR-03 applicability evidence a missing-material hard failure; no commits by user constraint).

Task 6: complete (no commits by user constraint; final focused suite 87/87 pass; full backend suite 247 pass / 4 skips; independent scoped re-review PASS).

Task 7: fix rounds 1–3 complete (malformed upload envelopes, staging error mapping, durable concurrent execution claim, rich list projection, cleanup diagnostics, exact A11 result-set validation, transaction rollback proof, restart durability and two immutable revisions addressed; no commits by user constraint).

Task 7: complete (no commits by user constraint; final focused suite 45/45 pass; full backend suite 274 pass / 4 skips; prior independent review findings closed by executable regression coverage; real DOC acceptance remains NO-GO).

Task 8: complete (no commits by user constraint; frontend contract suite 44/44 pass; static-serving suite 2/2 pass; full backend suite 276 pass / 4 skips; real synthetic-XLS browser flow completed through manual decisions, completion and reopen; 1440x900, 1280x720 and 760x900 visual checks PASS; explicit demo/template simulation boundaries visible).

Task 9: implementation complete / release NO-GO (no commits by user constraint; frozen matrix run `20260916T014614Z`; 17/17 source fingerprints unchanged; 15/17 inputs parsed; 15/15 business groups produced exactly 21 active results with no TR-05 result; G1/G4/G5/G6/G7/G8 GO; G2/G3 NO-GO because genuine Microsoft Word is unavailable; XLS trailing-space sheet-name defect and API parser-registration gap corrected with regression coverage; full backend suite 282 pass / 6 skips; frontend suite 44/44 pass).
