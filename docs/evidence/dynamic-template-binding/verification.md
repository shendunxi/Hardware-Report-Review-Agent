# Dynamic task-template binding verification

Date: 2026-09-17

Decision: **GO for local published-template task binding**

| Gate | Result | Evidence |
| --- | --- | --- |
| Published selection | PASS | Task API accepts a published `template_id`; unknown and non-published versions are rejected. |
| Frozen binding | PASS | Task persists template identity, source hash and the complete rule JSON snapshot at creation. |
| Historical stability | PASS | An A12 task continued after its selected template was retired. |
| Dynamic execution set | PASS | Test A12 disabled TR-02 and executed exactly 20 frozen enabled rules. |
| Safe unknown-rule behavior | PASS | Modified TR-01 produced `NEEDS_REVIEW` with `TEMPLATE_RULE_REQUIRES_MANUAL_REVIEW`; no old automatic result was reused. |
| Dynamic export | PASS | After manual resolution, the retired-template task exported an A12 XLS copy from its frozen source and rules. |
| Source protection | PASS | Dynamic writer verifies the frozen source SHA-256 and tests assert the source hash is unchanged. |
| Regression | PASS | Backend: 303 passed, 8 skipped. Frontend: 51 passed. Node syntax checks passed. |
| Live migration | PASS | Development SQLite upgraded from Alembic `0002` to `0003 (head)` without rebuilding the database. |
| Live compatibility | PASS | Server returned HTTP 200 for the UI, template list and existing completed A11 export; existing task reports 21 frozen-compatible rules and exported 54,784 bytes. |
| Baseline integrity | PASS | Packaged A11 SHA-256 remained `E70BE939EBEB67CA44B9C734A6165DD15FE2F78B0782BDFBE99FAB3B3F534445`. |

## Remaining release boundaries

- No production LLM provider is configured; semantic checks continue to become `NEEDS_REVIEW` where deterministic evidence is insufficient.
- Role selection is still a UI permission demonstration, not server-side authentication/authorization.
- Production database selection and validation remain open.
- The supplied 17-file real-sample acceptance gate remains incomplete because the original environment could only fully parse 15 files.
