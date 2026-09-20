# A11 local vertical-slice release gates

Overall: **GO**

| Gate | Decision | Evidence |
|---|---|---|
| G1 Source protection | **GO** | 17/17 unchanged fingerprints |
| G2 Readability | **GO** | 17/17 parsed successfully |
| G3 Structural completeness | **GO** | all 17 normalized documents contain inventoried structure |
| G4 Rule completeness | **GO** | 15/15 groups have 21 active results |
| G5 Traceability | **GO** | every hard failure has evidence/missing material and every pending item has an unresolved reason |
| G6 Lifecycle | **GO** | backend suite passed=313 failed=0 skipped=6 recorded_at=2026-09-20T06:27:53+00:00; supplementary gate evidence accepted |
| G7 Performance | **GO** | all measured file parse + selected rule durations are <= 1200 seconds |
| G8 UI | **GO** | browser_verified=True recorded_at=2026-09-20T07:25:00+00:00 missing viewports=none; supplementary gate evidence accepted |

Machine-readable evidence: [sample-results.json](sample-results.json)  
Human-readable matrix: [sample-results.md](sample-results.md)  
Supplementary lifecycle/UI evidence: [gates.json](../gate-evidence/gates.json)  
Run record: [verification.md](verification.md)

## Unverified or deferred

G1-G5 and G7 are computed from this run. G6 and G8 are read from `docs/evidence/gate-evidence/gates.json` and report NOT_RUN when that evidence is absent, stale or incomplete -- they are never inferred from prose.

Real LLM calls, OCR, DOCX/XLSX real-sample compatibility, production database selection, authentication/authorization and formal A11 XLS writeback are not release-proven. Genuine Microsoft Word remains required for the acceptance-grade DOC gate; a Word-compatible host such as WPS is a development channel only, and the policy that produced this run is recorded in `sample-results.json`.
