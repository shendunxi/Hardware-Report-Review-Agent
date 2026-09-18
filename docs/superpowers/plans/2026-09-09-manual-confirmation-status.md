# Manual Confirmation Status Implementation Plan

> **状态：已被取代。** 2026-09-10 确认的设计允许人工修改任一系统初判；后续实施只使用 `docs/superpowers/plans/2026-09-10-a11-review-override-prototype.md`。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the approved “待人工确认” process state, require all pending items to be manually resolved before task completion or formal XLS export, and preserve the distinction between missing required evidence and inconclusive supplied evidence.

**Architecture:** Keep the prototype static and dependency-free. Treat the four item states as one review-state model, store manual resolutions as in-memory overrides, derive counts and completion gates from effective states, and keep XLS export limited to the three final states. Update every current requirements/design record so the historical three-state wording no longer contradicts the approved behavior.

**Tech Stack:** Markdown requirements, static HTML/CSS/JavaScript prototype, Node.js built-in test runner.

**Spec:** `docs/requirements/hardware-report-review-agent-prd-v0.1.md` plus the user-confirmed manual-confirmation decision dated 2026-09-09.

## Global Constraints

- Result item states are exactly: `符合`, `不符合`, `不适用`, `待人工确认`.
- Missing explicitly required evidence remains `不符合`; `待人工确认` is only for supplied evidence that rules and AI cannot resolve, or rules intentionally designated for human judgment.
- A manual reviewer must convert every `待人工确认` item to one of the three final states and leave a review note before task completion.
- Formal XLS export is unavailable while any pending item remains; XLS mapping remains D/E/F for the three final states, with evidence/review notes in G.
- Rule administrators may save and publish human-review rules; incomplete automation criteria produce warnings, not publication blockers.
- No issue severity, `无法判断`, or `接受例外` state may be introduced.
- Do not initialize Git or create commits; the user explicitly cancelled repository setup.

---

### Task 1: Update the requirements contract

**Files:**
- Modify: `docs/requirements/hardware-report-review-agent-prd-v0.1.md`
- Modify: `docs/requirements/template-field-dictionary-v0.1.md`
- Modify: `docs/requirements/template-check-rules-v0.1.md`

**Interfaces:**
- Consumes: the approved state semantics in Global Constraints.
- Produces: one consistent business contract used by design records and prototype tests.

- [x] **Step 1: Replace three-state-only wording**

Add `待人工确认` as a process state while preserving `符合/不符合/不适用` as final/export states.

- [x] **Step 2: Add manual resolution acceptance criteria**

Specify reviewer role, required final selection, review note, reviewer identity, review time, zero-pending completion gate, and formal-export gate.

- [x] **Step 3: Correct inconclusive-evidence behavior**

Keep missing explicitly required material as `不符合`; route supplied but inconclusive evidence to `待人工确认` without fabricated locations.

- [x] **Step 4: Add anti-gaming metrics**

Set proposed automatic decision coverage to `≥90%`, pending-item rate to `≤10%`, final error rate to `≤5%`, and end-to-end P95 including manual resolution to `≤20 minutes`, each labeled according to confirmed versus inferred status.

- [x] **Step 5: Review the three documents for contradictions**

Run:

```powershell
rg -n "只有.*符合.*不符合.*不适用|仅展示符合|证据无法唯一定位.*不符合|修正以下.*才能发布" docs/requirements
```

Expected: no unqualified three-state-only or publication-blocking wording remains.

### Task 2: Write failing prototype acceptance tests

**Files:**
- Modify: `prototype/a11-ui/tests/prototype.test.js`

**Interfaces:**
- Consumes: exact labels and gates from Task 1.
- Produces: regression checks for `demo-data.js`, `app.js`, CSS, README, layout comparison, design spec, and historical plan.

- [x] **Step 1: Replace the three-status data test**

Assert that `statuses` contains all four states and still excludes `无法判断` and `接受例外`.

- [x] **Step 2: Add workflow-gate checks**

Assert that the prototype contains a pending sample, manual final-state controls, review note, reviewer/time record, pending-count gate, disabled task completion, and disabled formal export.

- [x] **Step 3: Add rule-publication warning checks**

Assert that incomplete automated criteria are described as warnings and human-review routing rather than hard publication blockers.

- [x] **Step 4: Run the new tests and observe failure**

Run:

```powershell
node --test prototype/a11-ui/tests/prototype.test.js
```

Expected: FAIL against the current three-state prototype.

### Task 3: Implement the prototype state and manual review flow

**Files:**
- Modify: `prototype/a11-ui/demo-data.js`
- Modify: `prototype/a11-ui/app.js`
- Modify: `prototype/a11-ui/styles.css`
- Modify: `prototype/a11-ui/README.md`

**Interfaces:**
- Consumes: `DEMO_DATA.statuses`, rule initial statuses, and the manual-resolution acceptance tests.
- Produces: effective rule statuses, review counts, manual review records, task completion gate, and export gate.

- [x] **Step 1: Add a representative pending rule**

Use TR-16 as the supplied-but-inconclusive example with status `待人工确认`, evidence already present, and a finding that neither the configured rule nor AI can substantiate the required ordering.

- [x] **Step 2: Derive effective statuses from manual overrides**

Add in-memory `manualReviews`, calculate displayed rules and counts from overrides, and keep the original demo data immutable.

- [x] **Step 3: Render the fourth status**

Add pending badge, count card, filter, explanatory content, and accessible visual styling.

- [x] **Step 4: Add manual resolution controls**

For a pending item, render a required review-note field and three actions: `确认符合`, `确认不符合`, `确认不适用`. On selection, store final status, note, reviewer `陈工`, and the prototype review time, then re-render the workbench.

- [x] **Step 5: Gate completion and formal export**

Disable `完成审核` and `导出正式审核副本` while pending count is greater than zero, show the remaining count, and enable both after the final pending item is resolved.

- [x] **Step 6: Replace rule publication blockers with warnings**

Keep structural diagnostics visible, allow publication, explain that affected rules will enter manual review, and add `需人工复核` as a judgment-method choice.

- [x] **Step 7: Run tests until green**

Run:

```powershell
node --test prototype/a11-ui/tests/prototype.test.js
```

Expected: all tests pass.

### Task 4: Update historical design records and compare surface

**Files:**
- Modify: `docs/superpowers/specs/2026-09-08-hardware-report-review-ui-prototype-design.md`
- Modify: `docs/superpowers/plans/2026-09-08-hardware-report-review-ui-prototype.md`
- Modify: `prototype/hardware-report-review-layout-options.html`

**Interfaces:**
- Consumes: the finalized terminology and workflow from Tasks 1 and 3.
- Produces: no historical artifact that incorrectly asserts a three-state-only workflow.

- [x] **Step 1: Mark the historical decision change**

Add a 2026-09-09 change note explaining that the earlier three-state-only decision is superseded by four in-process states and three final/export states.

- [x] **Step 2: Update workflow and acceptance text**

Add the pending-item manual resolution path, completion/export gates, and non-blocking rule warnings.

- [x] **Step 3: Update the layout comparison sample**

Add a visible `待人工确认` count and adjust sample totals without introducing excluded states or severity.

- [x] **Step 4: Run the complete test suite**

Run:

```powershell
node --test prototype/a11-ui/tests/prototype.test.js
```

Expected: all tests pass across prototype and current records.

### Task 5: Browser verification

**Files:**
- Verify: `prototype/a11-ui/index.html`
- Verify: `prototype/a11-ui/app.js`
- Verify: `prototype/a11-ui/styles.css`

**Interfaces:**
- Consumes: the completed static prototype.
- Produces: observable proof that the interaction matches the written acceptance criteria.

- [x] **Step 1: Open the local prototype**

Use the existing local preview server at `http://127.0.0.1:8766/?v=final` if available; otherwise start the documented static server.

- [x] **Step 2: Verify the blocked state**

Open the result workbench, filter `待人工确认`, select TR-16, and confirm that completion and formal export are disabled with one pending item.

- [x] **Step 3: Resolve the pending item**

Enter a review note, choose one of the three final states, and confirm that reviewer/time information appears and pending count becomes zero.

- [x] **Step 4: Verify completion/export and responsive layout**

Confirm that completion and formal export become available, the XLS dialog only summarizes the three final statuses, and the workbench remains usable at 1440×900 and 1280×720.
