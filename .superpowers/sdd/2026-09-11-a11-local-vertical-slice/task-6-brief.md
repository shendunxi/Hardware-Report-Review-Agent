# Task 6 Brief — A11 registry, atomic checks, and priority engine

## Objective

Implement the frozen A11 rule registry and a deterministic, evidence-traceable local rule engine. It must expose all 22 source rows, execute exactly 21 rules with TR-05 disabled, apply the confirmed hard-failure priority, and route semantic uncertainty to `NEEDS_REVIEW` because no LLM is used in this phase.

## Source of truth

- `docs/requirements/template-check-rules-v0.1.md` — exact rule IDs, source rows, summaries, requirements, materials, main judgment types, boundaries, priority, override semantics.
- `docs/requirements/template-field-dictionary-v0.1.md` — A11 row visibility, 22/21 invariant, dual status model.
- `docs/superpowers/specs/2026-09-11-a11-local-vertical-slice-design.md` section 6.
- `docs/superpowers/plans/2026-09-11-a11-local-vertical-slice.md` Task 6.
- Existing normalized documents, `EvidenceLocator`, `AtomicResult`, `RuleResult`, `StagedFile`, `EvidenceKind`, and clock/persistence contracts.

If this brief and a summarized phrase differ, the two requirements documents above win. Do not reinterpret historical report content as a gold standard.

## Binding boundaries

- No Git, LLM, OCR, external API, invented policy, inferred severity, parser changes, API/UI work, or real-sample accuracy claims.
- Do not fabricate naming rules, homepage fields, model/region/use-case mappings, sorting criteria, coating expectations, applicability, or evidence locations.
- A required external evidence item that is absent is `NON_COMPLIANT`, unless the frozen rule explicitly says missing business criteria/legality basis must be `NEEDS_REVIEW`.
- A proven objective failure stays `NON_COMPLIANT` even when semantic questions remain.
- `NOT_APPLICABLE` requires explicit traceable evidence proving all checks in that source row are inapplicable; silence never proves N/A.
- `COMPLIANT` is allowed only where all applicable objective and semantic obligations are positively proven without an LLM. AI-only rules TR-13/TR-16/TR-17/TR-18 cannot become `COMPLIANT` from rule matching alone in this phase.
- Every `NON_COMPLIANT` result has at least one evidence locator or an explicit missing-material record. Every `NEEDS_REVIEW` result has a concrete unresolved-semantic reason.
- Strict TDD by rule group.

## Files

Create:

- `backend/src/hw_review/rules/__init__.py`
- `backend/src/hw_review/rules/a11_registry.py`
- `backend/src/hw_review/rules/a11_engine.py`
- `backend/tests/unit/test_a11_registry.py`
- `backend/tests/unit/test_a11_priority.py`
- `backend/tests/unit/test_a11_rules.py`
- `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-6-report.md`

Modify only as required:

- `backend/src/hw_review/domain/models.py` and `domain/__init__.py` for minimal immutable `RuleDefinition`, `ReviewSource`, and `ReviewInput` contracts.
- `backend/src/hw_review/domain/ports.py` only for the exact `DocumentQuery` protocol below; do not weaken existing protocols.

Do not modify requirements/design/plan, parsers, staging/cleanup, persistence, prototype, or prior tests.

## Registry contract

- `A11Registry.source_rows() -> tuple[RuleDefinition, ...]`
- `A11Registry.executed_rules() -> tuple[RuleDefinition, ...]`
- `A11Registry.get(rule_id) -> RuleDefinition`

`RuleDefinition` must freeze at least: rule ID, A11 source row, source sequence, exact summary, exact verifiable requirement, exact required-material wording, main judgment (`RULE`, `RULE_PLUS_AI`, `AI`, `DISABLED`), confirmed boundary, enabled flag, and registry/baseline version.

Encode rows exactly: TR-01 at row 10; TR-02..TR-22 at rows 13..33; TR-05 is row 16/sequence 5 and `enabled=False`/`DISABLED`. Source rows stay ordered; executed rules preserve order and exclude only TR-05. Unknown IDs fail stably. No extra aliases or rules.

## Query and input contract

Use the exact protocol:

```python
class DocumentQuery(Protocol):
    def find_text(self, patterns: tuple[str, ...]) -> tuple[EvidenceLocator, ...]: ...
    def find_nonempty_labels(self, labels: tuple[str, ...]) -> dict[str, EvidenceLocator]: ...
    def has_evidence_kind(self, kind: EvidenceKind) -> bool: ...
```

Provide a conservative implementation over `ReviewSource` + normalized `ReportDocument`:

- literal, case-insensitive text matching only; no regex supplied by untrusted input;
- searches cell display text and text blocks, returns stable de-duplicated locators in source/container/block order;
- label lookup counts a field only when a matching label and a traceable nonempty value can be established from the normalized structure; mere occurrence of a label is not a filled value;
- evidence-kind routing comes only from supporting-source metadata, never from filename guessing;
- every locator uses the original source-file ID, source container, structural address, quoted text when available, and content hash.

`ReviewInput` must carry task ID, active revision number, ordered sources/documents, an aware evaluation timestamp or injected clock value, and the query boundary. Validate one or more primary report sources and consistent source/document IDs. Fakes implementing `DocumentQuery` are permitted for exhaustive rule branch tests; production engine behavior must not special-case test fakes.

## Priority and aggregation

Implement `rollup(atoms) -> AtomicResult` with this exact logic:

1. Return `NOT_APPLICABLE` only when every atom is proven `NOT_APPLICABLE`.
2. Otherwise any required-material or objective-hard-failure `NON_COMPLIANT` atom makes the row `NON_COMPLIANT`.
3. Otherwise any `NEEDS_REVIEW` atom makes the row `NEEDS_REVIEW`.
4. Otherwise all remaining applicable atoms must be `COMPLIANT`, so return `COMPLIANT`.

Reject an empty atom list. Merge all evidence, missing materials, and unresolved semantics from every atom without dropping lower-priority diagnostics; de-duplicate deterministically. `basis_code` and `basis_text` must remain stable and explain the selected branch.

## Rule implementation policy

Encode the 21 rules directly from the frozen table; do not create new criteria. Use small named atomic checks. The following routing is binding where it clarifies ambiguity:

- **TR-01:** missing `JIRA_RECORD` is `NON_COMPLIANT`; report/JIRA evidence present but link legality cannot be proven from a published criterion is `NEEDS_REVIEW`; never invent a URL pattern.
- **TR-02:** missing `PREVIOUS_STAGE_REPORT` is `NON_COMPLIANT`; otherwise issue/status/regression correspondence remains semantic and is `NEEDS_REVIEW` unless every relation is positively represented by test-provided evidence.
- **TR-03:** when software FAIL applicability is evidenced, missing `JIRA_RECORD`/handling record is `NON_COMPLIANT`; closure/notification correspondence is semantic. No-Fail N/A requires explicit evidence.
- **TR-04:** typical and standby power fields plus `POWER_RECORD` are objective; any missing item is `NON_COMPLIANT`; all three proven may be `COMPLIANT`. TR-05 contributes no result.
- **TR-06:** explicit proof of no internal capability limitation may yield N/A; otherwise missing requirement/capability/outsourcing proof is `NON_COMPLIANT`; adequacy of reasons/arrangement remains semantic.
- **TR-07:** absent published naming/version criterion is the explicitly confirmed `NEEDS_REVIEW` case, not invented failure; missing report version/project/stage data is objective `NON_COMPLIANT`; comparison to supplied criterion may remain semantic.
- **TR-08:** absent published homepage required-field list is `NEEDS_REVIEW`; with a supplied list, missing/blank declared fields are `NON_COMPLIANT`; cross-body consistency is semantic.
- **TR-09:** absent model/region/standard/use-case mapping is `NEEDS_REVIEW`; once mapping exists, missing task model/region evidence or objectively missing mandatory case is `NON_COMPLIANT`; full semantic mapping is not guessed.
- **TR-10:** missing required test-item/case evidence is `NON_COMPLIANT`; visible blank required data or an unreasoned unexecuted item is `NON_COMPLIANT`; do not claim completeness without a supplied checklist.
- **TR-11:** missing `PAPER_RECORD` is `NON_COMPLIANT`; invalid numeric format with a locator is `NON_COMPLIANT`; cross-record equality requires evidence and may remain semantic.
- **TR-12:** missing report data/summary/conclusion is `NON_COMPLIANT`; their consistency is semantic and normally `NEEDS_REVIEW` here.
- **TR-13:** required original/log/problem/summary material absent is `NON_COMPLIANT` when explicitly required; with material present, no-omission/no-summary-loss remains `NEEDS_REVIEW`; never `COMPLIANT` without LLM/manual review.
- **TR-14:** proven non-EMC applicability may yield N/A; applicable or unresolved-applicability cases require applicability evidence. Missing `EMC_REPORT` or `JIRA_RECORD` where applicable is `NON_COMPLIANT`; margin below 3 dB is objective `NON_COMPLIANT`; semantic anomaly correspondence remains pending.
- **TR-15:** missing current stage or required `PREVIOUS_STAGE_REPORT` is `NON_COMPLIANT`; conflict explanation remains semantic.
- **TR-16:** absent published ordering criterion is `NEEDS_REVIEW`; even with it, emphasis/order judgment remains `NEEDS_REVIEW` without LLM. Do not introduce severity.
- **TR-17:** missing problem-list material or an objectively absent one of the four fixed elements (test object, condition, observed phenomenon, actual result) is `NON_COMPLIANT`; adequacy remains semantic; no invented fifth element.
- **TR-18:** missing conclusion/problem material is `NON_COMPLIANT`; whether one conclusion expresses one independently actionable issue remains `NEEDS_REVIEW`; never rule-only compliant.
- **TR-19:** explicit non-applicability may yield N/A; missing applicability evidence is `NON_COMPLIANT`; applicable case requires `TEMPERATURE_RECORD`, otherwise `NON_COMPLIANT`; present objective record/result may be `COMPLIANT`.
- **TR-20:** missing stage evidence is `NON_COMPLIANT`; explicitly non-PP is N/A; PP requires `AUTOMATION_RECORD` and a result, otherwise `NON_COMPLIANT`; all proven may be `COMPLIANT`.
- **TR-21:** explicit non-WIFI scope may yield N/A; WIFI report requires both small conclusion and top-of-page conclusion nonblank, otherwise `NON_COMPLIANT`; only presence is checked, not consistency.
- **TR-22:** explicit non-applicability may yield N/A; missing `TEMPERATURE_RECORD`/photo-like traceable evidence where applicable is `NON_COMPLIANT`; absent published coating expectation with materials present is `NEEDS_REVIEW`; comparison remains semantic without LLM.

Where the fixed `EvidenceKind` vocabulary has no dedicated category, require traceable report/support text and use `OTHER` only when the uploaded file was explicitly tagged `OTHER`; never infer its meaning from the filename.

## Engine output

`A11Engine.evaluate(review_input) -> tuple[RuleResult, ...]`:

- returns exactly 21 results in registry order, never TR-05;
- each result uses the input task ID, active revision, aware evaluation time, frozen engine/baseline version, definition rule ID, rolled-up initial status, basis, evidence, missing materials, and unresolved semantics;
- stable deterministic result IDs derive from task/revision/rule/engine identity rather than randomness;
- evaluating identical input twice yields semantically identical ordered results.

## Required TDD coverage

1. Registry exact 22 rows/21 execution set, exact IDs/order/source rows/main judgment/wording, TR-05 disabled, no aliases, stable unknown lookup.
2. Priority matrix including all-NA, NA+compliant, NA+pending, pending+hard failure, evidence/missing/unresolved merge/dedup, and empty rejection.
3. For every executed rule, table-driven tests cover: each required-material absence; at least one objective failure where the baseline defines one; N/A only where allowed and explicitly proven; unresolved semantic branch; and compliant branch only where rule-only proof is permitted.
4. Explicit assertions that AI-only TR-13/TR-16/TR-17/TR-18 never return rule-only `COMPLIANT`.
5. Every noncompliant result contains locator or missing material; every pending result contains unresolved semantics.
6. Real document-query tests prove literal matching, adjacent/nonempty label semantics, deterministic ordering/dedup, evidence-kind routing, original source IDs, and no filename inference.
7. Representative all-rules inputs always return exactly 21 ordered results, stable IDs, no TR-05, and deterministic repeat output.
8. Full backend regression remains green; compileall passes.

## Report

`task-6-report.md` must include RED/GREEN commands and counts, exact registry checksum or complete row matrix, a 21-row branch/evidence/status matrix, priority tests, invariant/determinism evidence, exact files, limitations, and no Git commit. Clearly state that semantic rules are pending because the LLM is intentionally absent, not because they passed.

## Completion gate

Task 6 completes only when all 22 definitions match the frozen baseline, exactly 21 results are produced, TR-05 is excluded, every status is evidence/diagnostic-valid under the confirmed priority, exhaustive branch tests and full regression pass, and independent review finds no invented rule criterion.
