# A11 Checklist Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a real download that writes the latest completed review snapshot into a new A11 `.xls` checklist copy.

**Architecture:** A dedicated export service validates the completed task and immutable revision snapshot, delegates legacy-XLS copying and cell writes to a focused writer, and returns bytes to one FastAPI download endpoint. The real-mode frontend exposes a same-origin download link only for completed tasks.

**Tech Stack:** Python 3.12, FastAPI, xlrd, xlwt, xlutils, Node.js built-in test runner.

**Spec:** `docs/superpowers/specs/2026-09-17-a11-checklist-export-design.md`

## Global Constraints

- Never modify the source report or authoritative A11 template.
- Only `COMPLETED` tasks may export, using the latest immutable completed revision snapshot.
- Final statuses are exactly `COMPLIANT`, `NON_COMPLIANT`, and `NOT_APPLICABLE`.
- Source-row mapping comes from `A11Registry`; TR-05 remains untouched.
- Do not run Git commands or create commits, per the user's explicit instruction.

---

### Task 1: Legacy XLS writer

**Files:**
- Create: `backend/src/hw_review/services/a11_export.py`
- Create: `backend/tests/unit/test_a11_export.py`
- Modify: `backend/pyproject.toml`
- Create: `backend/resources/a11/hardware-test-process-checklist-a11.xls`

**Interfaces:**
- Consumes: `A11Registry.executed_rules()` and a completed `ReviewRevision.result_snapshot` JSON string.
- Produces: `A11ChecklistWriter.render(snapshot: str) -> bytes` and stable `ChecklistExportError` codes.

- [ ] **Step 1: Write failing tests** for exact D/E/F/G mapping, TR-05 preservation, template SHA-256 preservation, A11 structure rejection, and invalid snapshot rejection.
- [ ] **Step 2: Run the focused unit test** and confirm failure because the export module does not exist.
- [ ] **Step 3: Add the authoritative A11 template copy and `xlutils` dependency.**
- [ ] **Step 4: Implement the minimal writer** using `xlrd.open_workbook(..., formatting_info=True)` and `xlutils.copy.copy`, writing only D:G for enabled registry rows.
- [ ] **Step 5: Run the focused unit test** and confirm all writer contracts pass.

### Task 2: Completed-revision export service and API

**Files:**
- Modify: `backend/src/hw_review/config.py`
- Modify: `backend/src/hw_review/api/app.py`
- Modify: `backend/src/hw_review/api/routes/tasks.py`
- Modify: `backend/src/hw_review/api/errors.py`
- Modify: `backend/tests/integration/test_task_api.py`

**Interfaces:**
- Consumes: `RepositoryBundle.tasks`, `RepositoryBundle.revisions`, configured A11 template path, and `A11ChecklistWriter`.
- Produces: `GET /api/tasks/{task_id}/export` with legacy-XLS bytes and attachment headers.

- [ ] **Step 1: Write failing API tests** for the completed-state gate, successful XLS download, safe filename, latest revision use, and stable template errors.
- [ ] **Step 2: Run the focused API tests** and confirm 404 or missing-service failures.
- [ ] **Step 3: Add `Settings.a11_template_path`** with the packaged authoritative template as the default.
- [ ] **Step 4: Implement `A11ChecklistExportService.export(task_id)`** and map repository/template/snapshot failures to stable `LifecycleError` values.
- [ ] **Step 5: Register the service and endpoint** and return `application/vnd.ms-excel` with UTF-8 attachment filename.
- [ ] **Step 6: Run the focused API tests** and confirm the endpoint contracts pass.

### Task 3: Real-mode user interface entry point

**Files:**
- Modify: `prototype/a11-ui/app.js`
- Modify: `prototype/a11-ui/tests/prototype.test.js`

**Interfaces:**
- Consumes: a completed real task ID.
- Produces: a visible same-origin link to `/api/tasks/{id}/export` labeled `导出测试检查表`.

- [ ] **Step 1: Write failing frontend tests** proving the link is visible for completed real tasks and absent for ready/failed tasks.
- [ ] **Step 2: Run the focused Node tests** and confirm the link assertions fail.
- [ ] **Step 3: Add the completed-only download link** to both real task detail and real review action areas while preserving the reopen action.
- [ ] **Step 4: Run the frontend tests** and confirm demo export behavior and real export visibility both pass.

### Task 4: Regression and workbook verification

**Files:**
- Modify: `docs/evidence/a11-local-vertical-slice/release-gates.md`

**Interfaces:**
- Consumes: the completed implementation and generated test workbook.
- Produces: fresh automated evidence and an explicit compatibility limitation if native Office/WPS opening is not verified.

- [ ] **Step 1: Run the full backend suite.** Expected: all tests pass with the export coverage included.
- [ ] **Step 2: Run the full frontend suite.** Expected: all tests pass with completed-only export visibility.
- [ ] **Step 3: Generate one representative export** from a controlled completed snapshot, reopen it with `xlrd`, and compare D:G values plus the source-template hash.
- [ ] **Step 4: Perform browser verification** on the running local app and confirm the completed-task page displays the download action.
- [ ] **Step 5: Update the release gate evidence** with commands, pass counts, source-template hash result, and any unverified native Office/WPS claim.

## Self-review

- Spec coverage: Tasks 1–4 cover workbook mapping, lifecycle gate, API response, UI entry, source preservation, and regression evidence.
- Placeholder scan: no TBD/TODO steps remain.
- Type consistency: the writer returns bytes; the service returns filename plus bytes; the route returns those bytes unchanged.
