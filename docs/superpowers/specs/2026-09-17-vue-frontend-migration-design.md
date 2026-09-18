# Vue frontend migration design

## 1. Decision and scope

The production-facing frontend moves to a new `frontend/` application built with Vue 3, Vite and TypeScript. The existing `prototype/a11-ui/` remains read-only as the accepted visual and interaction reference during migration. No backend business endpoint is renamed or replaced.

This first migration slice must deliver the complete real-API workflow already available at `http://127.0.0.1:8766/`:

- application shell and the approved role labels;
- dashboard and persisted task list;
- published-template selection and report/evidence upload;
- task execution status, failure diagnosis and polling;
- rule-result review, three human final statuses, required change reason, completion and reopen;
- completed XLS checklist download;
- template list, XLS upload, rule edit/add/delete, publish and retire.

The old `?mode=demo` in-memory workflow is not migrated into the production Vue application. The legacy prototype remains available as the comparison artifact, not as a second production state model.

## 2. Considered approaches

### Recommended: separate Vue application with a compatibility cutover

Create `frontend/`, consume the current `/api` contract, build to `frontend/dist`, and make FastAPI serve that directory when present. This isolates the migration, keeps rollback simple, and avoids mixing Vue state with the existing imperative DOM renderer.

### Rejected: incrementally mount Vue inside `prototype/a11-ui`

This would leave two state systems and two render paths in the same page. It lowers initial file count but makes behavior and cleanup harder to verify.

### Rejected: rewrite frontend and backend contract together

The current API is already regression-tested. Changing both sides would enlarge the failure surface without adding user value to this migration.

## 3. Architecture

- `src/api/`: typed HTTP and multipart client; converts non-2xx responses into stable `ApiError` objects.
- `src/stores/`: Pinia stores for session/role, tasks and templates. Server facts stay in stores; view-only selection/filter state stays in components.
- `src/router/`: routes for dashboard, tasks, create, review, templates and template editor, with permission-aware redirects.
- `src/components/`: reusable shell, state badges, error panel, source-file cards and loading/empty states.
- `src/views/`: one view per workflow page. Views orchestrate stores but do not issue raw `fetch` calls.
- `src/domain/`: TypeScript types and display helpers for task/template states and the four process statuses.

The application uses Vue Router history mode with FastAPI SPA fallback. API routes must continue to win over the frontend fallback.

## 4. State and data flow

1. Startup loads recent tasks and published template summaries.
2. Create view submits `template_id`, one primary report and aligned supporting-evidence metadata.
3. After creation, the task store requests execution and polls only transient states.
4. Review view derives final display status from the immutable system result plus the latest manual decision.
5. Completion remains blocked while any `NEEDS_REVIEW` result lacks a human final status.
6. Template changes refresh the template store; task pages never replace their frozen template facts with current template data.

## 5. UI and accessibility

The visual hierarchy, colors, spacing and desktop layout follow the approved scheme A prototype. Interactive controls use native buttons, labels and form fields; status is never conveyed by color alone. At widths below 760 px the content becomes one column without horizontal page scrolling.

All user-facing diagnostic text remains Chinese. Stable API error codes may be shown as secondary trace information.

## 6. Error handling

- API errors render the server message and stable code in a reusable error panel.
- Upload validation prevents submission without a published template, primary report, or evidence type for each supporting file.
- Polling stops on ready, failed or completed states and when leaving the task route.
- A failed task identifies the actual source filename when available and offers re-upload rather than retrying an unrecoverable staged task.

## 7. Build and serving

- Development: Vite on port 5173 proxies `/api` to FastAPI on port 8766.
- Integrated preview: `pnpm build` creates `frontend/dist`; FastAPI serves the built SPA at `/` and preserves `/api/*` routing.
- If `frontend/dist` is absent, FastAPI falls back to the legacy prototype so backend-only development remains usable.

## 8. Verification

- Vitest covers API multipart construction, derived review status, permission routing and store transitions.
- Vue Test Utils covers create-task template selection, completion gating, error rendering and template-rule actions.
- `vue-tsc --noEmit` must pass.
- `vite build` must pass.
- Existing backend and legacy frontend suites must remain green.
- Live smoke must verify `/`, `/api/tasks`, `/api/templates` and an existing completed-task export after cutover.

## 9. Explicit non-goals

- Server-side authentication and authorization.
- Production LLM provider integration.
- Production database selection.
- Redesigning the approved scheme A visual language.
- Changing the report parsing, rule semantics or XLS export contract.

