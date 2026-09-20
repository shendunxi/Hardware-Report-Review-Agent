# Interrupted-Execution Retry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the task detail view a correct, server-authoritative "重新执行" affordance for executions that were interrupted, closing the user-visible gap left by S1.

**Architecture:** `LifecycleService.execution_status(task)` becomes the single source of truth for reclaimability and is embedded in every task payload as a nullable `execution` object. The Vue detail view renders a retry panel from that field and calls the existing execute endpoint.

**Tech Stack:** Python 3.12, FastAPI, pytest, Vue 3, TypeScript, Pinia, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-20-interrupted-execution-retry-design.md`

## Global Constraints

- Do not add test files or test cases; extend existing test bodies only.
- Do not perform Git operations.
- Do not add a database migration or change the task state machine.
- Do not change any public error code or the `202` contract of `POST /api/tasks/{id}/execute`.
- Do not re-derive lease semantics on the client.
- Do not add automatic retry.
- Reuse the existing `.failure-panel` and `.button-row` styles; add no new CSS class.

---

### Task 1: Publish reclaimability from the service

**Files:** Modify `services/lifecycle.py`.

**Interfaces:** `LifecycleService.execution_status(task, now=None) -> dict | None`; `inspect_interrupted` reuses it.

- [x] Add `execution_status` returning `None` outside the interrupted states and `{reclaimable, seconds_until_reclaimable}` inside them.
- [x] Reimplement `inspect_interrupted` on top of it so the lease arithmetic exists once.
- [x] Keep `inspect_interrupted` free of writes.

### Task 2: Expose it on every task payload

**Files:** Modify `api/routes/tasks.py`.

**Interfaces:** `_task_payload(service, task, sources=())` adds `execution`.

- [x] Thread the lifecycle service into `_task_payload`.
- [x] Update every call site (create, execute, list, detail, complete, reopen).
- [x] Confirm the field is `null` for non-interrupted tasks.

### Task 3: Frontend contract and store action

**Files:** Modify `frontend/src/domain/types.ts`, `frontend/src/stores/tasks.ts`.

**Interfaces:** `TaskExecutionStatus`; `ReviewTask.execution`; `taskStore.reexecute(taskId)`.

- [x] Add the `TaskExecutionStatus` type and the `execution` field.
- [x] Add `reexecute` that calls the existing execute endpoint and then reloads the task.
- [x] Export `reexecute` from the store.

### Task 4: Retry panel in the task detail view

**Files:** Modify `frontend/src/views/TaskDetailView.vue`.

- [x] Render the panel only when `task.execution` is non-null.
- [x] Disable the button unless `reclaimable` is true, and explain the wait when it is false.
- [x] Reuse existing panel/button styles.

### Task 5: Extend assertions, verify, record

**Files:** Modify `backend/tests/integration/test_lifecycle.py`, `frontend/src/stores/tasks.spec.ts`; create `docs/evidence/interrupted-execution-retry/verification.md`; update this plan.

- [x] Extend the S1 lease block to assert `execution.reclaimable` is false while the lease holds, that the countdown is positive, and that `execution` is null once recovered.
- [x] Extend the task-store test to assert `reexecute` reuses the execute endpoint and reloads.
- [x] Run the full backend suite, frontend tests, typecheck and production build; record exact results.
- [x] Verify over real HTTP that the payload field flips with the lease and that re-execution converges.
- [x] Record that the view itself has no automated coverage and requires manual browser confirmation.
