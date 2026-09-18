# Task 6 Report — A11 registry, atomic checks, and priority engine

## Outcome

Implemented the frozen A11 registry and deterministic local rule engine. The registry exposes 22 source rows in A11 order, executes 21 rows, and never evaluates TR-05. The engine does not call an LLM. Semantic obligations that cannot be positively established by conservative literal/label/evidence-kind queries remain `NEEDS_REVIEW`; they are not reported as passing.

No Git repository or commit was created.

## TDD evidence

Runtime used for every command:

`C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`

| Cycle | RED command and observed result | GREEN command and observed result |
|---|---|---|
| Registry, priority, query, and initial A/B/C rule groups | `python -m pytest tests/unit/test_a11_registry.py tests/unit/test_a11_priority.py tests/unit/test_a11_rules.py -q` → 3 collection errors because `hw_review.rules`, `ReviewInput`, and `ReviewSource` did not exist | Same command → 49 passed after correcting two invalid normalized-document test fixtures (URL-encoded sheet prefix and digest construction; no production behavior was changed for those fixture errors) |
| Exact `DocumentQuery` typing, dynamic homepage required-field list, frozen baseline version, per-rule objective absences | `python -m pytest tests/unit/test_a11_rules.py -q` → 3 failed, 50 passed: query was typed as `object`, TR-08 did not inspect the supplied list, and results lacked `baseline_version` | Focused three-file command → 69 passed |
| Traceable label-based N/A, `PP阶段`, and embedded TR-22 records | `python -m pytest tests/unit/test_a11_rules.py -q` → 7 failed, 53 passed | Focused three-file command → 76 passed |
| Conservative coating evidence and explicit no-unexecuted-items handling | `python -m pytest tests/unit/test_a11_rules.py -q` → 4 failed, 58 passed | Focused three-file command → 78 passed |
| Review fix 1 — TR-10 declared required-data list | Focused selection → 1 failed, 1 passed, 62 deselected | Same selection → 2 passed, 62 deselected |
| Review fix 1 — TR-11 declared numeric list and decimal parsing | Focused selection → 1 failed, 1 passed, 64 deselected | TR-11 plus priority selection → 10 passed, 65 deselected |
| Review fix 1 — TR-20 explicit negative PP forms | Focused selection → 4 failed, 66 deselected | Positive and negative PP selection → 5 passed, 65 deselected |
| Review fix 1 — TR-03 missing FAIL basis | Focused selection → 1 failed, 70 deselected | TR-03 branch selection → 7 passed, 64 deselected |

Final focused verification:

`python -m pytest tests/unit/test_a11_registry.py tests/unit/test_a11_priority.py tests/unit/test_a11_rules.py -q`

Result after review fix round 1: **87 passed in 0.24s**.

Final full regression used an explicitly verified workspace-local pytest base directory because the default user temp directory was inaccessible in this managed Windows session:

`python -m pytest -q -rs --basetemp E:\Coding\Hardware-Report-Review-Agent\backend\.pytest-task6-fix1-20260915`

Result after review fix round 1: **247 passed, 4 skipped in 18.75s**. Two skips require Windows symbolic-link privilege and two skips report `NO-GO` because `Word.Application` is not registered to Microsoft `WINWORD.EXE` in this runtime. These skips are existing environment gates, not A11 rule passes.

Compile verification:

`python -m compileall -q src tests`

Result: exit code 0, no output.

## Registry evidence

Canonical JSON serialization of all `RuleDefinition` fields, UTF-8 encoded with compact separators:

- Source rows: 22
- Executed rules: 21
- SHA-256: `cf3df816356e53bf3da9c5da9e0a72246758a50c5b0cc1c14231f216684945eb`

| Rule | Source row | Sequence | Main judgment | Enabled |
|---|---:|---:|---|---|
| TR-01 | 10 | 1 | RULE | yes |
| TR-02 | 13 | 2 | RULE_PLUS_AI | yes |
| TR-03 | 14 | 3 | RULE_PLUS_AI | yes |
| TR-04 | 15 | 4 | RULE | yes |
| TR-05 | 16 | 5 | DISABLED | no |
| TR-06 | 17 | 6 | RULE_PLUS_AI | yes |
| TR-07 | 18 | 7 | RULE | yes |
| TR-08 | 19 | 8 | RULE_PLUS_AI | yes |
| TR-09 | 20 | 9 | RULE | yes |
| TR-10 | 21 | 10 | RULE | yes |
| TR-11 | 22 | 11 | RULE | yes |
| TR-12 | 23 | 12 | RULE_PLUS_AI | yes |
| TR-13 | 24 | 13 | AI | yes |
| TR-14 | 25 | 14 | RULE_PLUS_AI | yes |
| TR-15 | 26 | 15 | RULE_PLUS_AI | yes |
| TR-16 | 27 | 16 | AI | yes |
| TR-17 | 28 | 17 | AI | yes |
| TR-18 | 29 | 18 | AI | yes |
| TR-19 | 30 | 19 | RULE | yes |
| TR-20 | 31 | 20 | RULE | yes |
| TR-21 | 32 | 21 | RULE | yes |
| TR-22 | 33 | 22 | RULE_PLUS_AI | yes |

The unit test contains the complete literal matrix for exact ID, row, sequence, summary, verifiable requirement, required-material wording, main judgment, and enabled state. It also verifies baseline `A11`, registry `a11-registry-1`, source/execution order, TR-05 exclusion, and stable failure for aliases or unknown IDs.

## Priority and diagnostic evidence

| Atomic statuses | Rolled-up status | Stable basis |
|---|---|---|
| all `NOT_APPLICABLE` | `NOT_APPLICABLE` | `ROLLUP_ALL_NOT_APPLICABLE` |
| `NOT_APPLICABLE` + `COMPLIANT` | `COMPLIANT` | `ROLLUP_ALL_APPLICABLE_COMPLIANT` |
| any `NON_COMPLIANT`, including alongside pending | `NON_COMPLIANT` | `ROLLUP_HARD_FAILURE` |
| no hard failure and any `NEEDS_REVIEW` | `NEEDS_REVIEW` | `ROLLUP_UNRESOLVED_SEMANTICS` |
| all remaining applicable atoms `COMPLIANT` | `COMPLIANT` | `ROLLUP_ALL_APPLICABLE_COMPLIANT` |

Tests prove empty aggregation is rejected and evidence locators, missing-material entries, and unresolved-semantic reasons are merged in atom order and deterministically de-duplicated even when a higher-priority status is selected.

## 21-rule branch/evidence/status matrix

| Rule | Objective or required-material branch | Explicit N/A branch | No-hard-failure result in this no-LLM phase | Rule-only `COMPLIANT` allowed |
|---|---|---|---|---|
| TR-01 | Missing tagged JIRA evidence or nonempty report JIRA link → NC | none | Link legality → NR | no; no URL rule is invented |
| TR-02 | Missing tagged prior-stage material → NC | none | Issue/status/regression correspondence → NR | no |
| TR-03 | Missing both FAIL list and explicit no-FAIL proof → NC; explicit software FAIL plus missing JIRA or handling explanation → NC | Explicit no software FAIL → N/A | Closure/manager-notification correspondence → NR | no |
| TR-04 | Missing typical power, standby power, or tagged power record → NC | none | all three objective facts present | yes |
| TR-06 | Missing requirement, capability limitation, or outsourcing arrangement → NC | Explicit no internal capability limitation → N/A | Reason/arrangement adequacy → NR | no |
| TR-07 | Missing report version, project, or stage → NC | none | Missing published rule or comparison to supplied rule → NR | no |
| TR-08 | Supplied published list names a blank/missing homepage field → NC with list locator | none | List absent/unreadable or body consistency unresolved → NR | no |
| TR-09 | Mapping present but model or region evidence missing → NC | none | Mapping absent or case correspondence unresolved → NR | no |
| TR-10 | Missing tagged checklist/case mapping, a field declared by traceable `必填数据清单`, or an unexecuted-item reason → NC | none | Unreadable/absent declared list and completeness comparison → NR | no |
| TR-11 | Missing tagged paper record or a field declared by traceable `数值字段清单` → NC; declared nonempty value with no parseable decimal → NC with `NUMERIC_FORMAT_INVALID` and value locator | none | Unreadable/absent numeric list and cross-record equality → NR | no |
| TR-12 | Missing report data, summary, or conclusion → NC | none | Their consistency → NR | no |
| TR-13 | Missing original record, log, problem list, summary, or conclusion → NC | none | No-omission/no-summary-loss → NR | never |
| TR-14 | Missing applicability, EMC/JIRA evidence, margin, invalid margin, or margin below 3 dB → NC | Explicit non-EMC applicability → N/A | Anomaly/JIRA correspondence → NR | no |
| TR-15 | Missing current stage or prior-stage report → NC | none | Cross-stage conflict explanation → NR | no |
| TR-16 | none invented | none | Ordering criterion absent or emphasis/order judgment unresolved → NR | never |
| TR-17 | Missing problem list or any of the four fixed elements → NC | none | Four-element adequacy → NR | never |
| TR-18 | Missing conclusion or problem list → NC | none | One independently actionable issue judgment → NR | never |
| TR-19 | Missing applicability, temperature record, or result → NC | Explicit non-applicability → N/A | all objective facts present | yes |
| TR-20 | Missing stage; PP missing automation record or result → NC | Explicit non-PP stage, including `非PP`, `非 PP`, `non-pp`, and `not pp`, → N/A before positive PP matching | PP with record and result | yes |
| TR-21 | Missing WIFI scope or either required conclusion field → NC | Explicit non-WIFI scope → N/A | WIFI with both fields nonempty | yes; presence only |
| TR-22 | Missing applicability, temperature record, or traceable CPU/tuner record → NC | Explicit non-applicability → N/A | Coating expectation absent or comparison unresolved → NR | no |

`NC` = `NON_COMPLIANT`, `NR` = `NEEDS_REVIEW`, `N/A` = `NOT_APPLICABLE`.

## Query and determinism evidence

- `ReviewInput.query` is typed to the exact runtime-checkable `DocumentQuery` protocol.
- Input validation requires at least one primary report, matching task IDs, and matching source/document IDs; timestamps are aware and normalized to UTC.
- Literal text matching is case-insensitive. User strings are never treated as regular expressions.
- Search results follow source/container/block/cell order and are deterministically de-duplicated.
- Spreadsheet labels count only when the immediate same-row value cell is nonempty; text labels count only for traceable `label: value` or `label：value` lines.
- Evidence kinds are read only from explicit `SUPPORTING_EVIDENCE.evidence_kinds`; a filename such as `JIRA_RECORD.pdf` does not create a JIRA tag.
- Every locator carries original source-file ID, container, structural address, quoted text where available, content hash, and bbox where available.
- Two evaluations of identical input produce equal ordered result tuples. UUID5 result identity is derived from task ID, active revision, rule ID, engine version, and A11 baseline rather than randomness.
- Tests assert exactly 21 ordered results, no TR-05, and frozen engine/baseline versions.
- Every `NON_COMPLIANT` result has evidence or a missing-material record. Every `NEEDS_REVIEW` result has an unresolved-semantic reason.

## Files created

- `backend/src/hw_review/rules/__init__.py`
- `backend/src/hw_review/rules/a11_registry.py`
- `backend/src/hw_review/rules/a11_engine.py`
- `backend/tests/unit/test_a11_registry.py`
- `backend/tests/unit/test_a11_priority.py`
- `backend/tests/unit/test_a11_rules.py`
- `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-6-report.md`

## Files modified

- `backend/src/hw_review/domain/models.py`
- `backend/src/hw_review/domain/ports.py`
- `backend/src/hw_review/domain/__init__.py`

## Limitations and explicit non-claims

- No LLM, OCR, external API, parser change, API/UI work, persistence migration, or report writeback was added.
- AI-only TR-13/TR-16/TR-17/TR-18 cannot return rule-only `COMPLIANT`; material-complete cases remain `NEEDS_REVIEW` because semantic review is intentionally absent.
- Dynamic business criteria are consumed only when traceably supplied. No naming convention, URL pattern, homepage field name, model/region/case mapping, severity/order rule, coating expectation, or applicability fact is invented.
- TR-10 and TR-11 parse field names only from traceable `必填数据清单` and `数值字段清单` values using conservative Chinese/ASCII comma, semicolon, ideographic-comma, or newline separators. An absent or unreadable list does not create field names and leaves the corresponding completeness/equality question pending.
- TR-22 accepts traceable embedded report records for the two named components; an `OTHER` evidence tag is used only when the user explicitly supplied it and is never inferred from a filename.
- The test evidence proves contract, branch, traceability, priority, and determinism behavior on controlled normalized inputs. It does not establish real-sample reading success, review accuracy, or production readiness.
