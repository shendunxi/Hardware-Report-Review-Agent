# Server-side Role Authorization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the frontend-only role demonstration with server-enforced local authorization and server-derived audit actors while preserving an explicit production-authentication NO-GO.

**Architecture:** A focused `access.py` module owns signed local-session tokens, access contexts and FastAPI dependencies. A session router issues loopback-only HttpOnly cookies, business routers require exact roles, and the Vue shell establishes or switches the local session before mounting route content. Production mode has no fake provider and rejects protected use until a real provider is supplied.

**Tech Stack:** Python 3.12 standard-library HMAC, FastAPI dependencies/cookies, Vue 3, Pinia, TypeScript.

**Spec:** `docs/superpowers/specs/2026-09-18-server-authorization-design.md`

## Global Constraints

- Do not add test files or test cases; only adjust existing fixtures/setup.
- Do not initialize, commit to or otherwise modify Git state.
- Do not modify the database schema in this slice.
- Do not claim production authentication is complete.
- Local role selection is permitted only for loopback clients.
- The browser must never provide a trusted audit actor directly.

---

### Task 1: Backend access context and signed local session

**Files:** Create `backend/src/hw_review/api/access.py` and `backend/src/hw_review/api/routes/session.py`; modify `config.py`, `errors.py`, and `app.py`.

**Interfaces:** Produce `AccessContext`, `LocalSessionCodec`, `require_authenticated`, `require_reviewer`, `require_template_manager`, `POST /api/session/local`, and `GET /api/session`.

- [x] Add explicit local/disabled authentication settings, 28,800-second TTL and `hw_review_session` cookie configuration.
- [x] Encode compact actor/roles/issued/expiry JSON with HMAC-SHA256; reject malformed, expired or modified tokens.
- [x] Restore local access from the cookie; disabled mode returns the legacy combined `local-review` context only for existing automated compatibility runs.
- [x] Enforce exact review/template roles and stable 401/403 error envelopes.
- [x] Issue HttpOnly, SameSite=Strict cookies only to loopback clients for tester/admin/combined selections.
- [x] Register the handler and session router before the SPA mount.

### Task 2: Enforce routes and trusted actors

**Files:** Modify task/template routes, `LifecycleService`, and existing backend fixture settings.

**Interfaces:** Change `save_decision(..., actor: str, supplemental_evidence=())`; remove template upload's multipart actor.

- [x] Require reviewer permission for every task operation.
- [x] Allow authenticated template reads and require template-manager permission for all mutations.
- [x] Persist the session actor for manual decisions and template upload.
- [x] Set existing backend app fixtures to `auth_mode="disabled"`; add no tests or assertions.
- [x] Run the unchanged backend suite with a system temporary base and require zero failures.

### Task 3: Establish and switch Vue sessions

**Files:** Modify domain types, API client, session store, app shell, template upload view, and only the setup of existing frontend specs.

**Interfaces:** Produce `SessionContext`, `selectLocalSession(role)`, `session.establish()`, and asynchronous `session.selectRole(role)`.

- [x] Send same-origin credentials and add the local-session API call.
- [x] Track server-confirmed role, actor, ready and error in Pinia.
- [x] Gate routed content until session establishment and make role switching asynchronous.
- [x] Replace the permission-demo label with “本地会话 · 服务端权限校验”.
- [x] Remove the editable template actor field.
- [x] Adjust existing fetch stubs only; keep the frontend test count at 17.
- [x] Run the unchanged frontend suite, typecheck and production build.

### Task 4: Runtime verification and evidence

**Files:** Create `docs/evidence/server-authorization/verification.md`; update Vue migration evidence.

- [x] Restart the integrated service on `127.0.0.1:8766`.
- [x] Verify real-cookie 401/403 boundaries for tester, admin and combined sessions.
- [x] Verify manual-decision actor is server-derived without leaving unverifiable persistent data.
- [ ] Verify browser role switching and forbidden-route behavior.
- [x] Record exact unchanged test counts and the continuing production-authentication/template-audit NO-GO.
- [x] Re-run the unchanged backend/frontend suites, typecheck and production build.
