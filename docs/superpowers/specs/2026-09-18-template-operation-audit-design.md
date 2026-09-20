# Template Operation Audit Design

## Goal

Record every user-driven template upload, rule creation, rule update, rule deletion, publication and retirement as an immutable application-level event with the trusted server actor, UTC time, template version and before/after business snapshots.

## Scope

- Audit actions: `TEMPLATE_UPLOADED`, `RULE_CREATED`, `RULE_UPDATED`, `RULE_DELETED`, `TEMPLATE_PUBLISHED`, `TEMPLATE_RETIRED`.
- The built-in A11 baseline registration is not a user upload and does not create a synthetic historical event.
- Events are append-only through the application: no update or delete repository/API operation exists.
- Only the template-manager role may read the audit timeline.
- The template editor displays the timeline newest first.
- No general-purpose system audit center, export, search or retention scheduler is added in this slice.

## Data Model

Alembic revision `0004` adds `template_audit_events`:

- `id`: UUID text primary key.
- `template_id`: required foreign key to `template_versions` with delete restricted.
- `template_version`: required immutable version label.
- `action`: one of the six supported action values.
- `rule_id`: nullable affected rule identifier.
- `actor`: required trusted server-session display identity.
- `occurred_at`: required UTC timestamp.
- `before_json` / `after_json`: nullable canonical JSON business snapshots.

Template snapshots contain name, version, status, source filename/hash, source-row count and effective-rule count. Rule snapshots contain the editable rule fields and source mapping. Managed filesystem paths are excluded.

## Write Flow

Routes pass `principal.actor` to every template mutation. The template service validates and constructs the event. Repository mutation methods append the event in the same SQL transaction as the primary template or rule write. Failed validation, authorization or database mutation creates no event.

Rule-count refresh remains a derived template update; it is not a separate user-visible audit action. Publication and retirement status changes are persisted atomically with their audit events.

## Read Flow

`GET /api/templates/{template_id}/audit-events` requires template-manager permission and returns events newest first. The Vue template store loads the events with template detail, and the editor renders action, actor, time, affected rule and concise before/after changes.

## Error Handling

- Missing template returns the existing `TEMPLATE_NOT_FOUND` envelope.
- Empty actors are rejected before persistence.
- Unknown action values are rejected by both domain validation and the database check constraint.
- Audit insert failure rolls back the paired primary mutation.

## Verification

No test case or test file is added. The existing template API lifecycle test is extended first and must fail because the audit endpoint does not exist. It then verifies all six events, server-derived actor, snapshots, chronological persistence and restart recovery. Existing frontend tests are extended without increasing the 17-test count. Full backend/frontend regression, typecheck, production build and a live HTTP audit flow are required.

