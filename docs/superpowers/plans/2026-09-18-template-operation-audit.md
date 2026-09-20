# Template Operation Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a server-trusted, append-only audit timeline for all user-driven template and rule mutations.

**Architecture:** Alembic revision `0004` introduces a dedicated audit-event table. Domain events are created by `TemplateService`, persisted in the same transaction as the primary mutation, exposed by a template-manager-only API, and rendered in the existing Vue template editor.

**Tech Stack:** Python 3.12, SQLAlchemy Core, Alembic, FastAPI, Pydantic, Vue 3, Pinia, TypeScript.

**Spec:** `docs/superpowers/specs/2026-09-18-template-operation-audit-design.md`

## Global Constraints

- Do not add test files or test cases; extend existing test bodies only.
- Do not perform Git operations.
- Do not expose managed absolute file paths in audit snapshots.
- Derive every actor from the authenticated server session.
- Create no audit event for failed mutations.
- Audit rows have no application update/delete operation.

---

### Task 1: Lock the backend contract with an existing test

**Files:** Modify `backend/tests/integration/test_template_api.py`.

**Interfaces:** `GET /api/templates/{template_id}/audit-events` returns `{ "events": [...] }` newest first.

- [x] Extend `test_template_api_upload_edit_publish_retire_and_restart` to read the audit timeline and assert the literal six-action sequence, `local-review` actor, affected rule IDs, before/after snapshots and restart persistence.
- [x] Run that single existing test and verify RED with HTTP 404 for the missing endpoint.

### Task 2: Add the audit domain and durable schema

**Files:** Modify `domain/enums.py`, `domain/models.py`, `domain/__init__.py`, `persistence/tables.py`, `persistence/repositories.py`; create `migrations/versions/0004_template_operation_audit.py`.

**Interfaces:** Produce `TemplateAuditAction`, `TemplateAuditEvent`, `SqliteTemplateAuditRepository.create()` and `.list_for_template()`; expose repository as `RepositoryBundle.template_audits`.

- [x] Add the six-value enum and Pydantic event model with timezone-aware UTC validation.
- [x] Add the table and migration with action constraint, template/rule indexes and restricted template foreign key.
- [x] Add canonical snapshot serialization/deserialization and append/list repository methods.
- [x] Run the existing test and verify it remains RED only because the route/write integration is missing.

### Task 3: Persist events atomically and expose the API

**Files:** Modify `persistence/repositories.py`, `services/templates.py`, `api/routes/templates.py`, and direct service callers in existing tests.

**Interfaces:** Mutation methods receive `actor: str`; repository mutation methods receive a `TemplateAuditEvent`; route `GET /{template_id}/audit-events` requires `require_template_manager`.

- [x] Pass `principal.actor` through rule update/add/delete, publish and retire routes.
- [x] Build sanitized before/after snapshots in `TemplateService`.
- [x] Insert each event inside the same SQL transaction as its primary mutation.
- [x] Return the audit timeline through the manager-only route.
- [x] Run the existing template API test and verify GREEN.
- [x] Run the unchanged backend suite.

### Task 4: Display the audit timeline in Vue

**Files:** Modify `frontend/src/domain/types.ts`, `frontend/src/api/client.ts`, `frontend/src/stores/templates.ts`, `frontend/src/views/TemplateEditorView.vue`, `frontend/src/styles.css`, and existing frontend spec setup/assertions only.

**Interfaces:** Produce `TemplateAuditEvent`, `ApiClient.listTemplateAuditEvents()`, and `templateStore.auditEvents`.

- [x] Extend one existing frontend test body so it fails on the missing audit timeline without increasing test count.
- [x] Add typed retrieval and load it with template detail.
- [x] Render newest-first Chinese action labels, actor, time, rule ID and concise changed-field summary.
- [x] Run the unchanged 17-test suite, typecheck and production build.

### Task 5: Runtime verification and evidence

**Files:** Create `docs/evidence/template-operation-audit/verification.md`; update this plan.

- [x] Upgrade the development SQLite database to Alembic `0004`.
- [x] Restart the integrated service on `127.0.0.1:8766`.
- [x] Exercise one temporary draft through all six mutation actions and verify server actor plus restart persistence, then remove only the temporary template data if cleanup is needed.
- [x] Verify reviewer access is HTTP 403 and template-manager access is HTTP 200.
- [x] Record exact test/build results and remaining production-authentication NO-GO.
