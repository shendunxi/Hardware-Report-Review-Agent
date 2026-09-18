# A11 local vertical slice — final review package

## Review verdict

**Implementation review: PASS within the declared local-only slice.**  
**Release gate: NO-GO.**

The implementation, test harness, browser integration and evidence package are internally consistent with the approved vertical-slice design. The release decision remains NO-GO because G2/G3 require 17/17 parser inputs, while the two legacy DOC primaries cannot be converted on a host where `Word.Application` resolves to Kingsoft WPS instead of genuine Microsoft Word.

Fresh final verification: backend `282 passed, 6 skipped`; frontend `44 passed`; compile check passed. The six backend skips are the four genuine-Word acceptance skips and two opt-in hard release-gate assertions.

This verdict does not claim completion of the full M1 PRD. The vertical slice explicitly excludes real LLM calls, OCR, DOCX/XLSX compatibility proof, template-management persistence, authentication/authorization, formal XLS writeback and a production database decision.

## Spec-compliance review

| Design obligation | Current evidence | Verdict |
|---|---|---|
| No Git initialization or use | repository has no `.git`; task records use `.superpowers/sdd` | PASS |
| Frozen sources remain read-only | final run reports 17/17 SHA-256, size and mtime fingerprints unchanged | PASS |
| Development database is SQLite; production TBD | `Settings.database_url` defaults to `sqlite:///./hw-review.db`; no production-specific adapter | PASS |
| No external LLM/OCR/formal XLS/auth/template backend in this slice | no LLM call site; boundaries are visibly documented/simulated | PASS |
| A11 has 22 source rows and 21 results; TR-05 is not executed | executable registry check returns 22/21 and no TR-05 result | PASS |
| System/final state sets stay exact | system has four states including `NEEDS_REVIEW`; final has only three | PASS |
| Rules prioritize hard failure and missing required evidence | rule-priority and real-matrix tests pass; traceability G5 is GO | PASS |
| Single-file work stays below 20 minutes and is measured | G7 GO; final evidence records parse/rule seconds and peak RSS, including failures | PASS |
| Task-local temporary data is cleaned | acceptance `_work` directory absent after run; guarded UUID-root cleanup is tested | PASS |
| Real task flow reaches the approved UI and survives restart | Task 8 browser flow, SQLite reload and three viewports passed | PASS |
| XLS/PDF/DOC adapters are connected to the real API | final review added a failing-then-passing PDF API regression and registered all three adapters | PASS |
| All 17 parser inputs normalize successfully | 15/17; S-06 and S-14 DOC fail with genuine-Word diagnostic | **NO-GO** |

## Task review summary

- Tasks 1–6: domain, staging safety, SQLite persistence, XLS/PDF/DOC parsing and deterministic A11 rules are complete with their recorded independent review fixes.
- Task 7: API lifecycle, concurrency claim, atomic result replacement, completion snapshots and reopen behavior are complete. Final spec review connected the already verified PDF/DOC adapters to the API.
- Task 8: real API frontend flow, manual override, completion/reopen, explicit demo mode and responsive layouts are complete; template screens remain visibly simulated.
- Task 9: frozen manifest, measurement runner, immutable-source proof, 15-group rules matrix and G1–G8 package are complete. The phase remains NO-GO rather than being mislabeled complete.

## Final-review corrections

1. Preserved trailing spaces in real XLS sheet names so container names and structural locators remain source-consistent. The new regression failed before the field-level fix and passed afterward.
2. Recorded elapsed time and peak memory for failed parses instead of leaving zero measurements. The failure-path regression failed before the timing fix and passed afterward.
3. Registered the verified PDF and DOC adapters in the real API; previously only XLS was registered even though the architecture and upload UI exposed the other formats. The new PDF API test failed as `FAILED`, then passed with `READY_FOR_REVIEW` and 21 results.

## Code-quality review

### Parser isolation

Format libraries remain inside adapter boundaries: `xlrd` is confined to the XLS parser, PyMuPDF to the PDF/DOC visual parser, and `win32com` is imported only by the short-lived Word child path. The rules layer consumes normalized documents and has no format-library imports.

### Filesystem safety

Staging uses generated UUID paths, content-based format checks, size/archive limits, source/copy fingerprints and cleanup on every failure path. Recursive task cleanup verifies a canonical UUID direct child under the resolved narrow root. DOC conversion rejects reparse-point escapes and binds every artifact to path, size, hash and conversion-attempt identity.

### Transaction boundaries

Evaluation replacement, failure persistence, completion snapshots and reopen copies use explicit database transactions. Exact 21-rule result-set validation happens before replacement; tests cover rollback, duplicate decisions, concurrent execution ownership and restart durability.

### Evidence integrity and test realism

The final matrix reads the supplied 17 files from staged copies, independently fingerprints every original afterward, uses no historical completed checklist as a gold standard and emits both machine-readable and human-readable evidence. Real browser testing used the live API and SQLite, not demo data. Hard release-gate assertions remain opt-in and deliberately fail while Word evidence is missing, so the normal suite cannot hide the NO-GO.

## Non-blocking engineering debt before networked production

- The local-only upload route reads each spooled upload into memory before staging enforces the configured file ceiling. Before allowing non-loopback access, stream ingress with an early byte limit and add request-size controls at the server/proxy boundary.
- Replace deprecated FastAPI `on_event` shutdown handling with lifespan management, and add Alembic `path_separator=os` to remove current deprecation warnings.
- Freeze production database, storage, retention, authentication and backup/restore choices before multi-user deployment.

## Required rerun to clear release NO-GO

Run the same frozen manifest on a host with genuine Microsoft Word. G2/G3 may be changed to GO only if both DOC inputs parse successfully, all 17 source fingerprints remain unchanged, every group still has exactly 21 active results, and the full automated/browser evidence remains valid.
