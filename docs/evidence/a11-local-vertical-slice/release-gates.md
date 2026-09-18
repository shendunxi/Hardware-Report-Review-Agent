# A11 local vertical-slice release gates

Overall: **NO-GO**

| Gate | Decision | Evidence |
|---|---|---|
| G1 Source protection | **GO** | 17/17 unchanged fingerprints |
| G2 Readability | **NO-GO** | 15/17 parsed successfully |
| G3 Structural completeness | **NO-GO** | one or more inputs lack a successful normalized structure |
| G4 Rule completeness | **GO** | 15/15 groups have 21 active results |
| G5 Traceability | **GO** | every hard failure has evidence/missing material and every pending item has an unresolved reason |
| G6 Lifecycle | **GO** | Task 7 focused 45 pass and full backend 274 pass / 4 skips |
| G7 Performance | **GO** | all measured file parse + selected rule durations are <= 1200 seconds |
| G8 UI | **GO** | Task 8 real browser flow and 1440x900/1280x720/760x900 checks passed |

Machine-readable evidence: [sample-results.json](sample-results.json)  
Human-readable matrix: [sample-results.md](sample-results.md)  
Automated-suite evidence: [Task 9 report](../../../.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-9-report.md)  
Lifecycle evidence: [Task 7 report](../../../.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-7-report.md)  
Browser evidence: [Task 8 report](../../../.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-8-report.md)

## Unverified or deferred

Real LLM calls, OCR, DOCX/XLSX real-sample compatibility, production database selection and authentication/authorization are not release-proven. Genuine Microsoft Word remains required for the DOC gate; WPS evidence is not accepted.

## A11 completed-checklist export gate (2026-09-17)

Decision: **GO for completed-task A11 XLS export**. This gate does not change the overall **NO-GO** decision above, which is still blocked by source-format parsing coverage.

| Check | Decision | Evidence |
|---|---|---|
| Completed-state gate | **GO** | The API rejects non-completed tasks; completed task `ecbbd0c8-86d5-45c4-aaca-6f282736f3c2` returned HTTP 200. |
| A11 result mapping | **GO** | Final `符合/不符合/不适用` values write to D/E/F; system basis, evidence, missing material and manual reason write to G. Human final decisions take precedence. |
| Template protection | **GO** | Packaged source template SHA-256 remained `E70BE939EBEB67CA44B9C734A6165DD15FE2F78B0782BDFBE99FAB3B3F534445`; export is generated as a new file. |
| Workbook structure | **GO** | Export reopened with `xlrd`: version `A11`, 2 sheets, 56 rows, 18 columns and 20 merged ranges; TR-05 source row remained unchanged. |
| Large evidence handling | **GO** | Evidence is de-duplicated and bounded to 50 traceable locations with an explicit omitted-count note; maximum observed G-cell length was 9,138 characters. |
| Chinese output | **GO** | Historical English basis strings are localized in the exported checklist; audit codes and source locators remain traceable. |
| Native spreadsheet open | **GO** | Microsoft Excel 12.0 opened the generated XLS read-only with 2 worksheets. |
| Automated regression | **GO** | Backend: 289 passed / 8 skipped. Frontend: 48 passed. |
| Browser visual check | **NOT RUN** | Browser automation was unavailable because the current Codex usage limit was reached. The completed-only export actions are covered by the 48-test frontend suite. |

## Persisted template-management gate (2026-09-17)

Decision: **GO for template upload, validation, draft-rule maintenance, publication and retirement**. Detailed evidence: [template-management verification](../template-management/verification.md).

The development database is at Alembic `0002`. Backend regression is 299 passed / 8 skipped; frontend regression is 50 passed. The packaged A11 source hash remains unchanged. Dynamic task-template binding, server-side authentication and production-database validation remain deferred, so this gate does not change the overall **NO-GO** decision above.

## Dynamic task-template binding gate (2026-09-17)

Decision: **GO for local published-template selection, frozen rule execution and version-bound XLS export**. Detailed evidence: [dynamic-template binding verification](../dynamic-template-binding/verification.md).

The development schema advances to Alembic `0003`. Backend regression is 303 passed / 8 skipped; frontend regression is 51 passed. Server-side authentication, a production LLM provider, production-database validation and the incomplete real-sample parsing gate remain deferred, so the overall release decision remains **NO-GO**.
