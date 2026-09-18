# Vue Frontend Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the production-facing imperative prototype with a typed Vue 3 application while preserving every verified real-API workflow and the approved scheme A appearance.

**Architecture:** A standalone `frontend/` Vite SPA uses typed API adapters, Pinia stores, permission-aware Vue Router routes, focused workflow views and shared components. FastAPI serves `frontend/dist` with SPA fallback and retains the legacy prototype only when no Vue build exists.

**Tech Stack:** Vue 3, TypeScript, Vite, Vue Router, Pinia, Vitest, Vue Test Utils, FastAPI static serving

**Spec:** `docs/superpowers/specs/2026-09-17-vue-frontend-migration-design.md`

## Global Constraints

- Preserve all existing `/api/tasks` and `/api/templates` request and response contracts.
- Use the role labels “测试报告审核” and “模板规则管理”.
- Process statuses are `COMPLIANT`, `NON_COMPLIANT`, `NOT_APPLICABLE`, `NEEDS_REVIEW`; human final status has only the first three.
- Never modify source reports or source templates.
- Keep `prototype/a11-ui/` intact as the comparison baseline.
- Do not perform Git operations.

---

### Task 1: Vue workspace and test harness

**Files:** Create `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig*.json`, `frontend/index.html`, `frontend/src/main.ts`, `frontend/src/App.vue`, `frontend/src/styles.css`, `frontend/src/test/setup.ts`, `frontend/src/App.spec.ts`.

**Interfaces:** Produces `pnpm test`, `pnpm typecheck`, and `pnpm build`; Vite proxies `/api` to port 8766.

- [ ] Write `App.spec.ts` asserting the application shell exposes the product name and both approved role labels.
- [ ] Run the test and observe failure because the Vue workspace does not exist.
- [ ] Add the minimal Vue/Vite/TypeScript scaffold and scheme A stylesheet import.
- [ ] Run the focused test, typecheck and build until all pass.

### Task 2: Typed domain and API boundary

**Files:** Create `frontend/src/domain/types.ts`, `frontend/src/domain/review.ts`, `frontend/src/api/client.ts`, `frontend/src/api/client.spec.ts`, `frontend/src/domain/review.spec.ts`.

**Interfaces:** Produces `apiClient`, `ApiError`, `deriveReviewRows(task)`, and typed task/template contracts.

- [ ] Write failing tests for aligned multipart task creation, stable API errors, and manual-final-status precedence.
- [ ] Implement the typed fetch client and pure review derivation helpers.
- [ ] Run focused tests, then the complete frontend suite.

### Task 3: Router, shell and permission state

**Files:** Create `frontend/src/router/index.ts`, `frontend/src/stores/session.ts`, `frontend/src/components/AppShell.vue`, `frontend/src/components/StatusBadge.vue`, `frontend/src/components/ErrorPanel.vue`, `frontend/src/router/router.spec.ts`; modify `frontend/src/App.vue`.

**Interfaces:** Produces named routes `dashboard`, `tasks`, `create-task`, `review`, `templates`, `template-editor`; `sessionStore` exposes review/template permissions.

- [ ] Write failing tests for tester/admin/combined navigation visibility and forbidden-route redirects.
- [ ] Implement the shell, route metadata and permission guard.
- [ ] Run router/component tests and typecheck.

### Task 4: Persisted task workflow

**Files:** Create `frontend/src/stores/tasks.ts`, `frontend/src/views/DashboardView.vue`, `frontend/src/views/TaskListView.vue`, `frontend/src/views/CreateTaskView.vue`, `frontend/src/views/TaskDetailView.vue`, `frontend/src/views/ReviewView.vue`, `frontend/src/stores/tasks.spec.ts`, `frontend/src/views/CreateTaskView.spec.ts`, `frontend/src/views/ReviewView.spec.ts`.

**Interfaces:** `taskStore` loads, creates, executes, polls, saves decisions, completes and reopens tasks; views consume only store methods.

- [ ] Write failing tests for published-template selection, evidence metadata validation, transient-only polling, human-decision precedence and unresolved-review completion gating.
- [ ] Implement the store and views with dynamic frozen rule totals and completed XLS download.
- [ ] Run focused tests, full tests, typecheck and build.

### Task 5: Persisted template administration

**Files:** Create `frontend/src/stores/templates.ts`, `frontend/src/views/TemplateListView.vue`, `frontend/src/views/TemplateEditorView.vue`, `frontend/src/stores/templates.spec.ts`, `frontend/src/views/TemplateEditorView.spec.ts`.

**Interfaces:** `templateStore` owns list/detail/upload/edit/add/delete/publish/retire operations and refreshes server facts after mutations.

- [ ] Write failing tests for draft-only mutations, blocking findings, non-blocking manual-review warnings and published/retired read-only states.
- [ ] Implement the template store and two administration views.
- [ ] Run focused tests, full tests, typecheck and build.

### Task 6: FastAPI cutover and regression gate

**Files:** Modify `backend/src/hw_review/api/app.py`, `backend/tests/integration/test_static_frontend.py`, `prototype/a11-ui/README.md`; create `frontend/README.md`, `docs/evidence/vue-frontend-migration/verification.md`.

**Interfaces:** FastAPI serves `frontend/dist/index.html` for non-API routes and falls back to `prototype/a11-ui` only when the build is absent.

- [ ] Write a failing backend integration test proving Vue assets and SPA fallback are served while `/api/*` still wins.
- [ ] Implement static-directory selection and SPA fallback.
- [ ] Run Vue tests/typecheck/build, backend full regression, legacy Node regression and live HTTP smoke checks.
- [ ] Record exact counts and remaining release boundaries in the evidence document.

