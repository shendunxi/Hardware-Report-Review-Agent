# Task 8 — real API frontend integration

## Scope and boundaries

- Default `/` mode now uses the seven same-origin Task 7 APIs. `?mode=demo` is the only static-data mode and is visibly labelled.
- The approved navigation, role names, A11 labels, status colors and three-column review workbench are preserved.
- Template management remains simulated and now carries a visible non-persistence banner. The role selector is explicitly labelled as a permission demonstration, not authentication.
- Frontend parsing, client-generated task IDs/results, wildcard CORS and production persistence were not introduced.

## QA inventory

| User-visible claim/control | Functional proof | Visual state |
|---|---|---|
| Default real API mode | `/api/tasks` loads on startup; no fabricated task ID | dashboard banner at 1440x900 and 1280x720 |
| Real upload | synthetic XLS selected with native file control; server returned 201 then execute 202 | create form before submission |
| 21 A11 results, no TR-05 result | task detail and review showed 21/21; source wording says TR-05 is not independently executed | dense review at 1440x900 and 1280x720 |
| Evidence traceability | TR-12 displayed XLS, filename, sheet and cell locator | center evidence column |
| Human override | TR-08 -> compliant, TR-09 -> not applicable, TR-16 -> noncompliant; every request returned 200 | system/final comparison and saved reason |
| Completion gate | completion disabled at three pending items, enabled at zero | review summary/action |
| Completion and reopen | completion created revision 1; reopen returned to three pending items and showed second-review toast | completed and reopened states |
| Explicit demo mode | `?mode=demo` showed fixed demo tasks and yellow `演示模式` banner | 1440x900 demo dashboard |
| Simulated template boundary | switching to `模板规则管理` removed review navigation and showed `模板管理模拟` | 1440x900 template list |
| Responsive layout | no horizontal document overflow; three columns at desktop and one stacked column at 760px | 1440x900, 1280x720, 760x900 |

Exploratory checks also covered a page reload after reopen (SQLite facts remained), narrow-screen scrolling to the evidence/manual-decision region, cache-busted assets, and the template-only role boundary.

## Browser evidence

- Synthetic task ID: `6ef98870-b4ca-452a-ae61-0d494e8f14ae`.
- HTTP sequence observed in the local server log: `POST /api/tasks` 201, `POST /execute` 202, task GET 200, three manual-decision PUTs 200, `POST /complete` 200, task GET 200, `POST /reopen` 200, task GET 200.
- Result state before manual review: 21 results, 18 noncompliant, 3 pending, no TR-05 result.
- Result state before completion: 1 compliant, 19 noncompliant, 1 not applicable, 0 pending.
- Reopen state: 21 copied system results, 3 pending human decisions, visible `第 2 次审核可继续处理` confirmation.

Viewport measurements:

| Viewport | Document width | Main/workbench evidence | Result |
|---|---:|---|---|
| 1440x900 | 1440 | workbench columns 274.625 / 529.656 / 321.719 px; each panel `scrollWidth == clientWidth` | PASS |
| 1280x720 | 1280 | workbench columns 258.547 / 452.484 / 298.969 px; each panel `scrollWidth == clientWidth` | PASS |
| 760x900 | 760 | main width 686 px; workbench one 641 px column; vertical page scrolling exposes evidence and decision regions | PASS |

The screenshots were inspected live in the in-app browser. No persistent screenshot artifact was created. The English basis text was given `overflow-wrap:anywhere` after the first visual pass exposed poor long-token wrapping.

## Automated verification

```text
node --check app.js                                      PASS
node --check api-client.js                               PASS
node --test tests/prototype.test.js                      44 passed
pytest tests/integration/test_static_frontend.py -q      2 passed
pytest -q                                                276 passed, 4 skipped
```

The four skips are the already documented honest DOC/Word acceptance skips. Real DOC acceptance remains NO-GO because genuine Microsoft Word is unavailable on this host.

## Findings corrected during Task 8

1. Alembic created `hw-review.db` while the application default opened `hw_review.db`; the application default now matches the migration configuration.
2. The Uvicorn README command omitted the `src/` import root; it now uses `--app-dir src`.
3. Demo mode was data-correct but not visibly labelled; every demo view now gets a persistent demo banner.
4. Template screens in real mode could be mistaken for persisted features; both screens now state that they are simulated.
5. Long rule-basis tokens wrapped poorly in the desktop decision panel; long content now wraps without horizontal overflow.

## Remaining boundaries

- Formal A11 XLS writeback/export remains a preview only.
- Template-management persistence, real authentication/authorization, LLM calls, OCR, DOCX/XLSX end-to-end compatibility and the production database remain deferred.
- The real DOC gate is still NO-GO; WPS is not accepted as Microsoft Word evidence.
