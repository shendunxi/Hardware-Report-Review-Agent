# Runtime Reliability and Configuration Externalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the permanent-stuck intermediate task state, wire the unused workspace expiry sweep, externalize configuration so migrations and runtime share one target, and close the `auth_mode="disabled"` network bypass.

**Architecture:** `claim_execution` gains a lease-expiry disjunct so an interrupted execution becomes reclaimable without any startup state mutation; `Settings` reads `HW_REVIEW_*` environment variables; `create_app` runs the existing expiry sweep once at startup and logs stuck tasks without mutating them.

**Tech Stack:** Python 3.12, SQLAlchemy Core, FastAPI, Pydantic, pytest.

**Spec:** `docs/superpowers/specs/2026-09-20-runtime-reliability-and-configuration-design.md`

## Global Constraints

- Do not add test files or test cases; extend existing test bodies only.
- Do not perform Git operations.
- Do not add a database migration; reuse `tasks.execution_claim` and `tasks.updated_at`.
- Do not modify `_NEXT` or `_transition()`; add no new forward transition.
- Do not change any public error code.
- Do not add dependencies (no `pydantic-settings`).
- `Settings` field defaults must stay byte-identical so existing tests constructing `Settings(...)` keep passing.
- Never log or embed `local_session_secret`.

---

### Task 1: Lease-based reclaim for interrupted executions

**Files:** Modify `persistence/repositories.py` (`SqliteTaskRepository.claim_execution`), `services/lifecycle.py` (`LifecycleService.__init__`, `request_execution`), `api/app.py` (pass the lease).

**Interfaces:** `claim_execution(task_id, *, now, lease_seconds)` becomes keyword-only and returns `ReviewTask | None`.

- [x] Widen the guarded `UPDATE` to `state == 'CREATED' OR (state IN (intermediate) AND updated_at <= stale_before)`.
- [x] Keep the write set identical: `state='FILES_STAGED'`, fresh `execution_claim`, `updated_at=now`.
- [x] Thread `execution_lease_seconds` from `Settings` into `LifecycleService`.
- [x] Confirm no caller outside the lifecycle service invokes `claim_execution`.

### Task 2: Startup visibility for stuck tasks

**Files:** Modify `services/lifecycle.py` (new `inspect_interrupted` method), `api/app.py`.

**Interfaces:** `LifecycleService.inspect_interrupted(now)` returns the intermediate-state tasks with remaining lease seconds; it performs **no writes**.

- [x] Add the read-only inspection helper.
- [x] Call it once in `create_app` and log a `WARNING` per interrupted task.
- [x] Verify the helper never mutates state (no repo write path).

### Task 3: Wire the workspace expiry sweep

**Files:** Modify `api/app.py`; consume `Settings.workspace_ttl_seconds`.

**Interfaces:** `WorkspaceCleaner(work_root, expiry=timedelta(seconds=workspace_ttl_seconds))`, then `clean_expired(now)` at startup.

- [x] Construct the cleaner with the configured TTL.
- [x] Call `clean_expired` once at startup; log the reclaimed task IDs.
- [x] Swallow and log sweep failures so startup is never blocked.
- [x] Confirm `clean_expired` is no longer dead code (a call site exists under `src/`).

### Task 4: Environment-driven settings

**Files:** Modify `config.py` (`Settings` fields, `get_settings`), `api/app.py` validation.

**Interfaces:** `get_settings()` reads `HW_REVIEW_*` and validates; `Settings(...)` direct construction keeps working unchanged.

- [x] Add `execution_lease_seconds` and `workspace_ttl_seconds` fields with the specified defaults.
- [x] Read every documented `HW_REVIEW_*` variable in `get_settings()`.
- [x] Reject unparsable or non-positive integers with a `ValueError` naming the variable.
- [x] Reject an empty `local_session_secret`.
- [x] Keep the `AUTH_PROVIDER_NOT_CONFIGURED` refusal for unknown `auth_mode`.
- [x] Align the runtime with `migrations/env.py`, which already reads `HW_REVIEW_DATABASE_URL`.

### Task 5: Restrict the unauthenticated bypass to loopback

**Files:** Modify `api/access.py` (`require_authenticated`).

**Interfaces:** `auth_mode="disabled"` yields the combined-role context only for `{"127.0.0.1", "::1"}` client hosts.

- [x] Add the loopback guard; otherwise raise `AccessError("PERMISSION_DENIED")`.
- [x] Confirm `AsgiClient` (`("127.0.0.1", 123)`) keeps every existing integration test green.

### Task 6: Extend existing assertions and record evidence

**Files:** Modify `tests/integration/test_lifecycle.py`, `tests/integration/test_sqlite_repository.py`, `tests/integration/test_task_api.py`; create `docs/evidence/runtime-reliability/verification.md`; update this plan.

- [x] Extend the lifecycle test: force a task into `PARSING`, re-request execution, assert convergence to `READY_FOR_REVIEW` with 21 results.
- [x] Extend the SQLite repository test: assert `get_settings()` honours `HW_REVIEW_DATABASE_URL` like the Alembic environment does.
- [x] Extend the task API fixture path: assert startup does not fail and the sweep runs.
- [x] Run the full backend suite and record the exact result.
- [x] Verify over real HTTP: lease reclaim, config from environment, loopback restriction.
- [x] Record that S1 does **not** close the user-visible gap until S1e adds a UI re-execute affordance.
