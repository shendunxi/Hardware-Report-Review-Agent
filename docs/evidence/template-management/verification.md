# Template management verification

Date: 2026-09-17  
Decision: **GO for persisted template administration**

## Verified scope

| Check | Result | Evidence |
|---|---|---|
| Schema migration | PASS | Development SQLite upgraded from Alembic `0001` to `0002`; `template_versions` and `template_rules` are present. |
| Baseline registration | PASS | Live `GET /api/templates` returned one published A11 version with 22 source rows and 21 enabled rules. |
| Read-only XLS validation | PASS | Packaged A11 validates without structural errors; A111, missing checklist sheet and version mismatch have stable blockers. |
| Managed copy | PASS | Uploaded XLS is copied to a template-ID directory; tests verified uploaded source SHA-256, size and mtime remain unchanged. |
| Draft lifecycle | PASS | Draft rules support add, edit, enable/disable and delete; counts are recomputed. |
| Publication lifecycle | PASS | Structural blockers prevent publication; published rules are immutable; retirement retains version and rules. |
| Restart recovery | PASS | Template version, validation findings and rules survive application/repository restart. |
| API | PASS | Upload, list, detail, update, add, delete, publish and retire operations passed integration tests with stable error envelopes. |
| Frontend | PASS | Real mode renders persisted versions/rules and uses template APIs; `?mode=demo` remains available. |
| Regression | PASS | Backend: 299 passed / 8 skipped. Frontend: 50 passed. |
| Existing task preservation | PASS | Migrated task `ecbbd0c8-86d5-45c4-aaca-6f282736f3c2` remained `COMPLETED`, revision 1; XLS export returned HTTP 200 and 54,784 bytes. |
| Source-template protection | PASS | Packaged A11 SHA-256 remained `E70BE939EBEB67CA44B9C734A6165DD15FE2F78B0782BDFBE99FAB3B3F534445`. |

## Explicitly not verified by this gate

- Selecting a published dynamic template when creating an audit task.
- Freezing a dynamic rule snapshot into the task and completed revisions.
- Executing or exporting newly added/deleted rules from a non-A11 version.
- Server-side authentication and role authorization.
- Production database compatibility.
- Real LLM calls and data-egress authorization.
- Browser visual automation in this run; the browser-control quota was unavailable, while the 50-test frontend suite passed.

Dynamic task-template binding was implemented and verified in the subsequent gate; see [dynamic-template binding verification](../dynamic-template-binding/verification.md).
