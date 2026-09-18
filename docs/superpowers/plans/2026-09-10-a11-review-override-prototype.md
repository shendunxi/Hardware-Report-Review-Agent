# A11 Review Override Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the current A11 interactive prototype so all system initial decisions can be manually changed with a required reason, pending items block completion, completed reviews are revisioned, and the UI consistently shows 22 source rows versus 21 executed checks.

**Architecture:** Keep the existing dependency-free browser prototype and its Node `vm` test harness. Separate immutable demo facts (`initialStatus`, evidence, 22 source rows) from mutable review decisions (`manualReviews`, completion revisions); derive all displayed/final states through pure helper functions before rendering. The prototype continues to simulate export and file upload and must never claim to perform real parsing, LLM calls, persistence, or XLS writes.

**Tech Stack:** HTML5, CSS3, vanilla JavaScript, Node.js built-in `node:test`, `assert`, and `vm`.

**Spec:** `docs/superpowers/specs/2026-09-10-a11-rule-baseline-and-validation-design.md`

## Global Constraints

- Formal template version is exactly `A11`; `A111` must not appear as a valid version.
- Keep exactly 22 source rows and 21 executed checks; `TR-05` is visible but `enabled: false` and is excluded from execution totals.
- System initial states are exactly `符合`, `不符合`, `不适用`, `待人工确认`; human final states are exactly `符合`, `不符合`, `不适用`.
- A user with review permission may change any executed item (`任一系统初判`); reason is required and supplemental evidence is optional.
- Any unresolved `待人工确认` item blocks completion; other untouched initial states are implicitly accepted at completion.
- Completed results cannot be overwritten; reopening creates the working state for a new revision while retaining earlier snapshots.
- Missing explicitly required external evidence remains an initial `不符合`; supplied but inconclusive evidence becomes `待人工确认`.
- UI and tests must not introduce severity, `无法判断`, or `接受例外`.
- Input copy lists PDF, DOC, DOCX, XLS, XLSX; the prototype must label upload and export as demonstrations, not real compatibility proof.
- Do not initialize Git or add commit steps; the user withdrew the Git request.

---

### Task 1: Freeze demo facts and permission capabilities

**Files:**
- Modify: `prototype/a11-ui/demo-data.js`
- Modify: `prototype/a11-ui/tests/prototype.test.js`

**Interfaces:**
- Produces: `DEMO_DATA.initialStatuses: readonly string[]`, `DEMO_DATA.finalStatuses: readonly string[]`, `DEMO_DATA.supportedInputFormats: readonly string[]`.
- Produces: role entries with `canReview: boolean` and `canManageTemplates: boolean`.
- Produces: rules with `initialStatus: string`, `enabled: boolean`, `sourceRow: number`, and the existing evidence fields.

- [ ] **Step 1: Repair the stale product-surface test inventory**

The current baseline is 13 passed and 1 failed because the test references deleted file `prototype/hardware-report-review-layout-options.html`. Replace that test's file list with current product surfaces only; do not scan planning documents because they intentionally name rejected states in negative requirements:

```js
const files = [
  'prototype/a11-ui/index.html',
  'prototype/a11-ui/demo-data.js',
  'prototype/a11-ui/app.js',
  'prototype/a11-ui/README.md',
  'docs/requirements/template-field-dictionary-v0.1.md',
  'docs/requirements/template-check-rules-v0.1.md',
  'docs/superpowers/specs/2026-09-08-hardware-report-review-ui-prototype-design.md'
];
```

Run: `node --test tests/prototype.test.js` from `prototype/a11-ui`  
Expected: the ENOENT failure disappears and the current suite reports 14 passed, 0 failed before behavior changes begin.

- [ ] **Step 2: Add failing data-contract tests**

Add a test that boots `demo-data.js` and asserts the exact status sets, format list, role capabilities, 22/21 counts, and `TR-05` behavior:

```js
test('A11 facts separate source rows, executed checks, statuses, formats and permissions', () => {
  const context = { window: {} };
  vm.runInNewContext(read('demo-data.js'), context);
  const data = JSON.parse(JSON.stringify(context.window.DEMO_DATA));

  assert.deepEqual(data.initialStatuses, ['符合', '不符合', '不适用', '待人工确认']);
  assert.deepEqual(data.finalStatuses, ['符合', '不符合', '不适用']);
  assert.deepEqual(data.supportedInputFormats, ['PDF', 'DOC', 'DOCX', 'XLS', 'XLSX']);
  assert.equal(data.rules.length, 22);
  assert.equal(data.rules.filter(rule => rule.enabled).length, 21);
  assert.equal(data.rules.find(rule => rule.ruleId === 'TR-05').enabled, false);
  assert.equal(data.roles.find(role => role.id === 'tester').canReview, true);
  assert.equal(data.roles.find(role => role.id === 'admin').canReview, false);
  assert.equal(data.roles.find(role => role.id === 'combined').canManageTemplates, true);
  assert.equal(data.roles.find(role => role.id === 'combined').canReview, true);
});
```

- [ ] **Step 3: Run the focused test and verify failure**

Run: `node --test --test-name-pattern="A11 facts separate" tests/prototype.test.js` from `prototype/a11-ui`  
Expected: FAIL because `initialStatuses`, `finalStatuses`, `supportedInputFormats`, capability fields, `combined`, and `initialStatus` are not yet defined.

- [ ] **Step 4: Implement immutable demo facts**

In `demo-data.js`, rename every rule property `status` to `initialStatus`, add each known workbook row number as `sourceRow`, and define the shared collections:

```js
const initialStatuses = Object.freeze(['符合', '不符合', '不适用', '待人工确认']);
const finalStatuses = Object.freeze(['符合', '不符合', '不适用']);
const supportedInputFormats = Object.freeze(['PDF', 'DOC', 'DOCX', 'XLS', 'XLSX']);

roles: Object.freeze([
  { id: 'tester', label: '测试报告审核', canReview: true, canManageTemplates: false },
  { id: 'admin', label: '模板规则管理', canReview: false, canManageTemplates: true },
  { id: 'combined', label: '测试报告审核 + 模板规则管理', canReview: true, canManageTemplates: true }
]),
initialStatuses,
finalStatuses,
supportedInputFormats,
```

Set `sourceRow` to 10 for TR-01, 13 through 33 for TR-02 through TR-22, and keep TR-05 as:

```js
{
  ruleId: 'TR-05', seq: 5, sourceRow: 16, title: '共享路径', method: '不执行',
  requirement: '源内容仅为共享路径，作为TR-04证据地址。', evidence: '并入TR-04',
  initialStatus: '不适用', enabled: false
}
```

Change task progress examples to use `/21`; keep template metadata `sourceRows: 22` and `effectiveRules: 21`.

- [ ] **Step 5: Run the focused and full contract tests**

Run: `node --test --test-name-pattern="A11 facts separate" tests/prototype.test.js`  
Expected: PASS.  
Run: `node --test tests/prototype.test.js`  
Expected: existing tests that still expect `status` or four-state `statuses` may FAIL; record those failures as the starting point for Task 2, while all unrelated shell/navigation tests remain PASS.

---

### Task 2: Introduce derived initial/final state and universal manual decisions

**Files:**
- Modify: `prototype/a11-ui/app.js`
- Modify: `prototype/a11-ui/tests/prototype.test.js`

**Interfaces:**
- Consumes: `DEMO_DATA.initialStatuses`, `DEMO_DATA.finalStatuses`, role capabilities, and rule `initialStatus` from Task 1.
- Produces: `currentRole(): Role`, `hasReviewPermission(): boolean`, `hasTemplatePermission(): boolean`.
- Produces: `effectiveRule(rule): EffectiveRule`, `reviewRules(): EffectiveRule[]`, `pendingReviewCount(): number`, `reviewCounts(): Record<string, number>`.
- Produces: `applyManualDecision(ruleId, finalStatus, reason, supplementalEvidence = ''): boolean`.

- [ ] **Step 1: Replace pending-only tests with universal-decision tests**

Add tests that cover all four initial states, required reason, optional evidence, permissions, and history preservation:

```js
test('review permission can change any executed initial state without erasing it', () => {
  const { app } = bootPrototype();
  assert.equal(app.applyManualDecision('TR-01', '不符合', ''), false);
  assert.equal(app.applyManualDecision('TR-01', '不符合', '人工核对后发现链接并非目标项目。'), true);
  const changed = app.reviewRules().find(rule => rule.ruleId === 'TR-01');
  assert.equal(changed.initialStatus, '符合');
  assert.equal(changed.finalStatus, '不符合');
  assert.equal(changed.manualReview.reason, '人工核对后发现链接并非目标项目。');
  assert.equal(changed.manualReview.supplementalEvidence, '');
});

test('template-only role cannot change review results but combined role can', () => {
  const { app } = bootPrototype();
  app.setRole('admin');
  assert.equal(app.applyManualDecision('TR-02', '符合', '业务确认材料在系统外有效。'), false);
  app.setRole('combined');
  assert.equal(app.applyManualDecision('TR-02', '符合', '业务确认材料在系统外有效。'), true);
});

test('non-executed source row cannot receive a manual decision', () => {
  const { app } = bootPrototype();
  assert.equal(app.applyManualDecision('TR-05', '符合', '不应执行'), false);
});
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `node --test --test-name-pattern="change any|template-only|non-executed" tests/prototype.test.js`  
Expected: FAIL because `applyManualDecision`, `reviewRules` export, capabilities, and the new effective-state properties do not exist.

- [ ] **Step 3: Implement the state derivation helpers**

Replace the local `finalStatuses` constant with `data.finalStatuses`. Add:

```js
function currentRole() {
  return data.roles.find(role => role.id === state.role);
}

function hasReviewPermission() {
  return Boolean(currentRole()?.canReview);
}

function hasTemplatePermission() {
  return Boolean(currentRole()?.canManageTemplates);
}

function canNavigate(view) {
  if (['dashboard', 'tasks', 'create-task', 'review'].includes(view)) return hasReviewPermission();
  if (['templates', 'rule-editor'].includes(view)) return hasTemplatePermission();
  return false;
}

function effectiveRule(rule) {
  const manualReview = state.manualReviews[rule.ruleId] || null;
  const implicitFinal = rule.initialStatus === '待人工确认' ? null : rule.initialStatus;
  const finalStatus = manualReview ? manualReview.status : implicitFinal;
  return {
    ...rule,
    finalStatus,
    displayStatus: finalStatus || rule.initialStatus,
    manualReview
  };
}

function pendingReviewCount() {
  return reviewRules().filter(rule =>
    rule.enabled && rule.initialStatus === '待人工确认' && !rule.manualReview
  ).length;
}
```

Make `reviewCounts()` exclude disabled TR-05 and count `displayStatus`. Update filtering and badges to use `displayStatus`.

Replace role-ID navigation checks with capabilities: `navigate(view)` returns when `!canNavigate(view)`; `renderSidebar()` renders the review group only when `hasReviewPermission()` and the template group only when `hasTemplatePermission()`; `setRole()` sends the user to the first permitted view if the current view becomes unavailable. This makes `tester`, `admin`, and `combined` demonstrate review-only, template-only, and permission-union behavior.

- [ ] **Step 4: Implement universal manual decision validation**

Replace `resolveManualReview` with:

```js
function applyManualDecision(ruleId, finalStatus, reason, supplementalEvidence = '') {
  const rule = data.rules.find(item => item.ruleId === ruleId);
  const normalizedReason = String(reason || '').trim();
  if (
    !hasReviewPermission() || state.taskCompleted || !rule || !rule.enabled ||
    !data.finalStatuses.includes(finalStatus) || !normalizedReason
  ) return false;

  state.manualReviews[ruleId] = {
    status: finalStatus,
    reason: normalizedReason,
    supplementalEvidence: String(supplementalEvidence || '').trim(),
    reviewer: '陈工',
    reviewedAt: '今天 17:18'
  };
  render();
  return true;
}
```

Export `currentRole`, permission helpers, `effectiveRule`, `reviewRules`, `pendingReviewCount`, and `applyManualDecision` through `window.prototypeApp`.

- [ ] **Step 5: Run all state tests**

Run: `node --test --test-name-pattern="change any|template-only|non-executed|pending review|three final states" tests/prototype.test.js`  
Expected: PASS after renaming the old `resolveManualReview` assertions to `applyManualDecision` and preserving rejection of `待人工确认` and `接受例外` as final states.

---

### Task 3: Redesign the result workbench for initial-versus-final review

**Files:**
- Modify: `prototype/a11-ui/app.js`
- Modify: `prototype/a11-ui/styles.css`
- Modify: `prototype/a11-ui/tests/prototype.test.js`

**Interfaces:**
- Consumes: `EffectiveRule.initialStatus`, `.displayStatus`, `.finalStatus`, and `.manualReview` from Task 2.
- Produces: action `data-action="save-manual-decision"` with inputs `manual-final-status`, `manual-review-reason`, and `manual-review-evidence`.

- [ ] **Step 1: Add failing rendered-UI assertions**

```js
test('every executed result exposes initial state and an editable final decision', () => {
  const { app, elements } = bootPrototype();
  app.navigate('review');
  app.selectRule('TR-01');
  const html = elements.get('app-main').innerHTML;
  assert.match(html, /系统初判/);
  assert.match(html, /人工最终状态/);
  assert.match(html, /id="manual-final-status"/);
  assert.match(html, /id="manual-review-reason"/);
  assert.match(html, /id="manual-review-evidence"/);
  assert.match(html, /data-action="save-manual-decision"/);
  assert.match(html, /修改原因.*必填/s);
  assert.match(html, /补充证据.*选填/s);
});

test('disabled evidence-address row is visible but has no decision form', () => {
  const { app, elements } = bootPrototype();
  app.navigate('review');
  app.selectRule('TR-05');
  const html = elements.get('app-main').innerHTML;
  assert.match(html, /证据地址.*不独立执行/s);
  assert.doesNotMatch(html, /data-action="save-manual-decision"/);
});
```

- [ ] **Step 2: Run the rendered-UI tests and verify failure**

Run: `node --test --test-name-pattern="every executed|evidence-address" tests/prototype.test.js`  
Expected: FAIL because the current workbench only renders a form for `待人工确认`.

- [ ] **Step 3: Render initial and final status separately**

In `renderReviewWorkbench()`, keep all 22 source rows visible, label TR-05 as `证据地址 · 不独立执行`, and calculate the summary denominator with `data.rules.filter(rule => rule.enabled).length`. The detail header must show:

```js
<div class="decision-status-grid">
  <div><small>系统初判</small>${resultStatusBadge(selected.initialStatus)}</div>
  <div><small>人工最终状态</small>${selected.finalStatus ? resultStatusBadge(selected.finalStatus) : '<span>待人工处理</span>'}</div>
</div>
```

Render the edit form for every enabled rule when `hasReviewPermission()` and `!state.taskCompleted`; preselect the existing final status, require the reason field on submission, and label supplemental evidence as optional.

Use this form contract so event handlers and tests share stable IDs:

```js
const manualDecisionPanel = selected.enabled && hasReviewPermission() && !state.taskCompleted ? `
  <section class="manual-decision-form">
    <h3>人工最终判定</h3>
    <label><span>最终状态 <b>必填</b></span>
      <select id="manual-final-status">
        ${data.finalStatuses.map(status => `<option value="${status}" ${selected.finalStatus === status ? 'selected' : ''}>${status}</option>`).join('')}
      </select>
    </label>
    <label><span>修改原因 <b>必填</b></span>
      <textarea id="manual-review-reason" rows="3">${escapeHtml(selected.manualReview?.reason || '')}</textarea>
    </label>
    <label><span>补充证据 <em>选填</em></span>
      <textarea id="manual-review-evidence" rows="2">${escapeHtml(selected.manualReview?.supplementalEvidence || '')}</textarea>
    </label>
    <button class="btn btn-primary" data-action="save-manual-decision">保存人工判定</button>
  </section>` : '';
```

- [ ] **Step 4: Wire the save action**

Handle `save-manual-decision` by reading the three fixed IDs and calling:

```js
const success = applyManualDecision(
  state.selectedRuleId,
  document.getElementById('manual-final-status')?.value,
  document.getElementById('manual-review-reason')?.value,
  document.getElementById('manual-review-evidence')?.value
);
showToast(success ? '人工判定已保存' : '请选择最终状态并填写修改原因');
```

- [ ] **Step 5: Add focused visual styles**

Add `.decision-status-grid`, `.manual-decision-form`, `.manual-decision-record`, and `.source-row-disabled` styles. At `max-width: 760px`, collapse `.decision-status-grid` to one column. Reuse the existing status colors and focus-visible treatment; do not add a severity color.

- [ ] **Step 6: Run result-workbench tests**

Run: `node --test --test-name-pattern="executed result|evidence-address|review workbench|dashboard" tests/prototype.test.js`  
Expected: PASS with counts based on 21 executed checks and all 22 source rows still visible.

---

### Task 4: Add completion snapshots, reopen revisions, and export-preview mapping

**Files:**
- Modify: `prototype/a11-ui/app.js`
- Modify: `prototype/a11-ui/tests/prototype.test.js`

**Interfaces:**
- Produces: `completeReview(): boolean`, `reopenReview(): boolean`, `canExportReview(): boolean`.
- Produces: `buildExportRows(): Array<{ruleId, D, E, F, G}>`.
- Extends state with `reviewRevision: number` and `completedRevisions: RevisionSnapshot[]`.

- [ ] **Step 1: Add failing lifecycle and export tests**

```js
test('completion accepts untouched states, snapshots 21 checks and requires pending resolution', () => {
  const { app } = bootPrototype();
  assert.equal(app.completeReview(), false);
  assert.equal(app.applyManualDecision('TR-16', '符合', '人工确认顺序可接受。'), true);
  assert.equal(app.completeReview(), true);
  const state = app.getState();
  assert.equal(state.taskCompleted, true);
  assert.equal(state.completedRevisions.length, 1);
  assert.equal(state.completedRevisions[0].items.length, 21);
});

test('reopen keeps completed snapshot and creates the next revision', () => {
  const { app } = bootPrototype();
  app.applyManualDecision('TR-16', '符合', '首次复核。');
  app.completeReview();
  assert.equal(app.reopenReview(), true);
  assert.equal(app.getState().reviewRevision, 2);
  assert.equal(app.getState().completedRevisions.length, 1);
  assert.equal(app.applyManualDecision('TR-01', '不符合', '第二版修正。'), true);
  assert.equal(app.completeReview(), true);
  assert.equal(app.getState().completedRevisions.length, 2);
});

test('export rows use final status and preserve system basis plus human reason', () => {
  const { app } = bootPrototype();
  app.applyManualDecision('TR-16', '符合', '人工确认排序合理。');
  app.applyManualDecision('TR-01', '不符合', '链接指向错误项目。');
  app.completeReview();
  const row = app.buildExportRows().find(item => item.ruleId === 'TR-01');
  assert.deepEqual({ D: row.D, E: row.E, F: row.F }, { D: '', E: '╳', F: '' });
  assert.match(row.G, /JIRA项目页面截图/);
  assert.match(row.G, /链接指向错误项目/);
  assert.equal(app.buildExportRows().some(item => item.ruleId === 'TR-05'), false);
});
```

- [ ] **Step 2: Run lifecycle tests and verify failure**

Run: `node --test --test-name-pattern="completion accepts|reopen keeps|export rows" tests/prototype.test.js`  
Expected: FAIL because revision snapshots and export-row mapping do not exist.

- [ ] **Step 3: Implement completion and reopening**

Initialize:

```js
reviewRevision: 1,
completedRevisions: []
```

Add the following lifecycle functions; the JSON clone makes each completed revision independent of later edits:

```js
function completeReview() {
  if (!hasReviewPermission() || state.taskCompleted || pendingReviewCount() > 0) return false;
  const items = reviewRules().filter(rule => rule.enabled).map(rule => ({
    ruleId: rule.ruleId,
    initialStatus: rule.initialStatus,
    finalStatus: rule.finalStatus,
    manualReview: rule.manualReview
  }));
  state.completedRevisions.push(JSON.parse(JSON.stringify({
    revision: state.reviewRevision,
    completedBy: '陈工',
    completedAt: '今天 17:24',
    items
  })));
  state.taskCompleted = true;
  render();
  return true;
}

function reopenReview() {
  if (!hasReviewPermission() || !state.taskCompleted) return false;
  state.reviewRevision += 1;
  state.taskCompleted = false;
  render();
  return true;
}
```

- [ ] **Step 4: Implement export rows and gating**

```js
function canExportReview() {
  return hasReviewPermission() && state.taskCompleted && pendingReviewCount() === 0;
}

function buildExportRows() {
  if (!canExportReview()) return [];
  return reviewRules().filter(rule => rule.enabled).map(rule => ({
    ruleId: rule.ruleId,
    D: rule.finalStatus === '符合' ? '√' : '',
    E: rule.finalStatus === '不符合' ? '╳' : '',
    F: rule.finalStatus === '不适用' ? '⊙' : '',
    G: [rule.evidence, rule.finding, rule.manualReview?.reason]
      .filter(Boolean).join('；')
  }));
}
```

Make `openExportDialog()` require `canExportReview()`. Before completion show only `完成审核`; after completion show `导出正式审核副本` and `重新打开审核`. The dialog must state it is a prototype preview and show that D/E/F derive from final state while G includes system basis plus any human reason.

- [ ] **Step 5: Wire lifecycle actions and exports**

Replace direct `state.taskCompleted = true` click handling with `completeReview()`. Add handlers for `reopen-review` and keep `confirm-export` as a demonstration toast without file writes. Export the four Task 4 functions through `window.prototypeApp`.

- [ ] **Step 6: Run lifecycle and full tests**

Run: `node --test --test-name-pattern="completion accepts|reopen keeps|export rows" tests/prototype.test.js`  
Expected: PASS.  
Run: `node --test tests/prototype.test.js`  
Expected: PASS after updating old assumptions that export is available before completion.

---

### Task 5: Align formats, template counts, rule wording, and operator guidance

**Files:**
- Modify: `prototype/a11-ui/app.js`
- Modify: `prototype/a11-ui/demo-data.js`
- Modify: `prototype/a11-ui/README.md`
- Modify: `prototype/a11-ui/tests/prototype.test.js`

**Interfaces:**
- Consumes: `DEMO_DATA.supportedInputFormats` and template `sourceRows/effectiveRules`.
- Produces: one consistent UI label set: `22 个源行 · 21 个执行项`.

- [ ] **Step 1: Add failing copy-contract tests**

```js
test('all creation and template surfaces show the five formats and 22-to-21 baseline', () => {
  const source = read('app.js');
  for (const format of ['PDF', 'DOC', 'DOCX', 'XLS', 'XLSX']) {
    assert.match(source, new RegExp(format));
  }
  assert.match(source, /22 个源行/);
  assert.match(source, /21 个执行项/);
  assert.doesNotMatch(source, /22 个源校验项均已执行/);
});

test('approved A11 wording is present without invented rules', () => {
  const data = read('demo-data.js');
  assert.match(data, /软件测试团队经理/);
  assert.match(data, /对象、条件、现象和实际结果/);
  assert.match(data, /两处.*非空|小结论和页面顶端结论均非空/);
  assert.doesNotMatch(data, /A111/);
});
```

- [ ] **Step 2: Run copy tests and verify failure**

Run: `node --test --test-name-pattern="five formats|approved A11 wording" tests/prototype.test.js`  
Expected: FAIL on missing DOC/XLS UI copy, old 22-executed wording, and any missing approved text.

- [ ] **Step 3: Centralize format and count copy**

Build the upload label and shared count copy from data, instead of duplicating literals:

```js
const formatLabel = data.supportedInputFormats.join(' · ');
const sourceRowCount = data.rules.length;
const executedRuleCount = data.rules.filter(rule => rule.enabled).length;
const baselineLabel = `${sourceRowCount} 个源行 · ${executedRuleCount} 个执行项`;
```

Use `formatLabel` in upload help and `baselineLabel` in task/template screens; task progress uses `/21`. Keep TR-05 visible as a non-executed evidence-address row.

- [ ] **Step 4: Apply approved rule wording**

Update TR-03 to use `软件测试团队经理`, TR-17 to state the four required elements, and TR-21 to check only that both conclusions are filled. Keep the missing naming, homepage, mapping, sorting, and paint expectations as human-review warnings; do not invent values.

- [ ] **Step 5: Rewrite the README demonstration paths**

Document these exact flows:

1. Change a `符合` initial result to `不符合` with a reason and no supplemental evidence.
2. Resolve TR-16 pending, complete revision 1, preview export mapping, reopen, and complete revision 2.
3. Switch to template-only role and verify result editing is unavailable; switch to combined role and verify both navigation groups appear.
4. Explain that PDF/DOC/DOCX/XLS/XLSX upload and XLS export are simulated and are not real compatibility evidence.

- [ ] **Step 6: Run copy and full tests**

Run: `node --test tests/prototype.test.js`  
Expected: all tests PASS; excluded status and severity scans remain PASS.

---

### Task 6: Perform browser interaction and visual acceptance

**Files:**
- Modify only if defects are found: `prototype/a11-ui/app.js`
- Modify only if defects are found: `prototype/a11-ui/styles.css`
- Test: `prototype/a11-ui/tests/prototype.test.js`

**Interfaces:**
- Consumes: the complete prototype from Tasks 1-5.
- Produces: a verified local browser flow at 1440×900, 1280×720, and narrow-panel width ≤760px.

- [ ] **Step 1: Start the existing static preview server**

Run from `prototype/a11-ui`: `python -m http.server 8766 --bind 127.0.0.1`  
Expected: the server reports `Serving HTTP on 127.0.0.1 port 8766`; if `python` is not on PATH, use the workspace-bundled Python returned by the Codex workspace dependency loader.

- [ ] **Step 2: Verify the primary review flow at 1440×900**

Open `http://127.0.0.1:8766/?v=a11-review-override`. Select TR-01, change initial `符合` to final `不符合`, leave supplemental evidence blank, enter a reason, and save. Verify initial and final states remain simultaneously visible. Resolve TR-16, complete revision 1, open the export preview, reopen, make another change, and complete revision 2.

- [ ] **Step 3: Verify permissions and template counts at 1280×720**

Switch to `模板规则管理`; verify result editing is unavailable and template navigation shows A11 with 22 source rows and 21 executed checks. Switch to the combined-role option; verify both review and template navigation are present. Confirm there is no horizontal page scroll and no primary action is obscured.

- [ ] **Step 4: Verify responsive layout at ≤760px**

Verify navigation collapses, the review workbench and initial/final status cards become one column, status remains distinguishable by text, and every button/input has a visible keyboard focus indicator.

- [ ] **Step 5: Run final automated verification**

Run: `node --test tests/prototype.test.js`  
Expected: all tests PASS with zero failures.  
Run: `rg -n "无法判断|接受例外|严重性|A111|22 个源校验项均已执行" prototype/a11-ui`  
Expected: no product-copy matches; test-only negative assertions may contain the excluded words and must be reviewed rather than removed.

- [ ] **Step 6: Record bounded completion evidence**

In the implementation handoff, report the exact Node test result and the three inspected viewport sizes. State explicitly that the artifact is an interactive prototype: no real report parsing, LLM API call, persistence, authentication, or XLS file generation has been validated.

## Plan self-review

- Spec coverage: universal override, required reason/optional evidence, unresolved-pending gate, implicit acceptance, revision history, 22/21 counts, five input formats, role union, evidence semantics, export mapping, excluded states, and no source mutation are mapped to Tasks 1-6.
- Placeholder scan: the plan contains no deferred implementation placeholder; external production capabilities are explicitly out of prototype scope.
- Type consistency: all tasks use `initialStatus`, `finalStatus`, `displayStatus`, `manualReview.reason`, `manualReview.supplementalEvidence`, `reviewRevision`, and `completedRevisions` consistently.
- Verification boundary: Node and browser checks prove only prototype behavior and copy, not real parser, model, persistence, authorization, or workbook compatibility.
- Baseline defect accounted for: Task 1 first removes the stale reference to the deleted layout-options HTML; the plan does not assume the pre-change suite is already green.
