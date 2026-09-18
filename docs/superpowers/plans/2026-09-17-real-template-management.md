# Real Template Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace simulated template administration with a persisted A11-derived XLS upload, validation, draft-rule, publish and retire workflow.

**Architecture:** Add immutable template-version and version-scoped rule records to the existing SQLAlchemy Core repository bundle. A focused service owns read-only XLS validation, managed-copy storage and lifecycle rules; FastAPI exposes the service and the existing vanilla JavaScript page consumes it. The fixed A11 task engine remains unchanged in this slice.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLAlchemy Core, Alembic, SQLite, xlrd, vanilla JavaScript, Node test runner.

**Spec:** `docs/superpowers/specs/2026-09-17-real-template-management-design.md`

## Global Constraints

- Do not run Git commands or create commits.
- Source templates are read-only; store a new managed copy and never overwrite the user file.
- Only `.xls` template uploads are accepted.
- Published versions are immutable; retirement preserves history.
- `A111` is invalid and must not be normalized into a version.
- Authentication, production database selection, LLM calls and dynamic task-template binding are outside this slice.

---

### Task 1: Template domain and SQLite persistence

**Files:**
- Modify: `backend/src/hw_review/domain/enums.py`
- Modify: `backend/src/hw_review/domain/models.py`
- Modify: `backend/src/hw_review/domain/__init__.py`
- Modify: `backend/src/hw_review/persistence/tables.py`
- Modify: `backend/src/hw_review/persistence/repositories.py`
- Create: `backend/migrations/versions/0002_template_management.py`
- Modify: `backend/tests/integration/test_sqlite_repository.py`

**Interfaces:**
- Produces `TemplateStatus`, `TemplateVersion`, `TemplateRule`, `TemplateValidationFinding`, `SqliteTemplateRepository` and `RepositoryBundle.templates`.

- [x] Write failing migration and repository tests for create/list/get, version uniqueness, rule replacement, immutable published versions and restart recovery.
- [x] Run focused tests and confirm failures are caused by absent template tables/types.
- [x] Add the migration, domain types and transactional repository methods.
- [x] Run focused tests until green without changing task persistence behavior.

### Task 2: Read-only XLS validator and template lifecycle service

**Files:**
- Create: `backend/src/hw_review/services/templates.py`
- Modify: `backend/src/hw_review/services/__init__.py`
- Modify: `backend/src/hw_review/config.py`
- Create: `backend/tests/unit/test_template_service.py`

**Interfaces:**
- Produces `A11TemplateValidator.validate(path)`, `TemplateService.ensure_baseline()`, `upload()`, `detail()`, `update_rule()`, `add_rule()`, `delete_rule()`, `publish()` and `retire()`.

- [x] Write failing tests using the packaged A11 workbook and controlled invalid XLS fixtures.
- [x] Verify RED for legal A11, A111 rejection, missing-sheet blocker, source hash stability, draft edits, publish blocking and immutable published versions.
- [x] Implement validation, managed-copy storage and lifecycle methods with stable error codes.
- [x] Run the focused service tests until green.

### Task 3: Template management HTTP API

**Files:**
- Create: `backend/src/hw_review/api/routes/templates.py`
- Modify: `backend/src/hw_review/api/app.py`
- Modify: `backend/src/hw_review/api/errors.py`
- Create: `backend/tests/integration/test_template_api.py`

**Interfaces:**
- Produces the eight `/api/templates` operations defined by the spec.

- [x] Write failing API tests for upload, list/detail, edit/add/delete, publish, retire, restart recovery and stable errors.
- [x] Run the focused API file and confirm 404/missing-state failures.
- [x] Register the service and router, map multipart and JSON payloads, and preserve the existing error envelope.
- [x] Run API and existing task integration tests until green.

### Task 4: Connect the existing template pages to the API

**Files:**
- Modify: `prototype/a11-ui/api-client.js`
- Modify: `prototype/a11-ui/app.js`
- Modify: `prototype/a11-ui/README.md`
- Modify: `prototype/a11-ui/tests/prototype.test.js`

**Interfaces:**
- Produces real-mode template loading, upload, draft editing, publish and retire interactions while preserving `?mode=demo`.

- [x] Write failing Node tests that exercise real `ApiClient` template operations and observable real-mode rendering/actions.
- [x] Run the frontend suite and confirm only the new behaviors fail.
- [x] Add client methods and bind real-mode template list/editor state without changing demo behavior.
- [x] Run Node syntax checks and the complete frontend suite until green.

### Task 5: Full regression and evidence

**Files:**
- Modify: `docs/evidence/a11-local-vertical-slice/release-gates.md`
- Create: `docs/evidence/template-management/verification.md`

- [x] Apply migration `0002` to a disposable database and the development SQLite database.
- [x] Run all backend tests, all frontend tests and source-template hash comparison.
- [x] Restart the local service on port 8766 and verify the live baseline endpoint; upload/detail/publish/retire were verified through the real ASGI integration boundary against migrated SQLite.
- [x] Record exact counts and limitations; do not mark dynamic task-template binding or authentication complete.

## Plan self-review

- Spec coverage: persistence, validation, API, UI, source protection and restart recovery map to Tasks 1–5.
- Scope: dynamic task binding, generic evaluation and dynamic export are explicitly excluded and receive a separate plan.
- Type consistency: template version and rule types originate in Task 1; service, API and UI consume those exact persisted payloads.
- Placeholder scan: no implementation placeholder or unnamed error-handling step remains.
