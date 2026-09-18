# Hardware Report Review A11 UI Prototype Implementation Plan

> **状态：基础原型已实现，后续变更计划已取代本文件。** 2026-09-10 起，状态模型与原型修改只使用 `docs/superpowers/plans/2026-09-10-a11-review-override-prototype.md`。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a clickable desktop prototype that demonstrates the complete tester and template-rule-administrator workflows for the A11 hardware test report review product.

**Architecture:** A dependency-free browser application uses a single semantic HTML shell, a focused stylesheet, an immutable demo-data module, and a state-driven JavaScript renderer. Each screen is selected by application state so navigation, role visibility, task creation, four-state review handling, manual resolution, gated export feedback, and template administration can be verified without a backend.

**Tech Stack:** HTML5, CSS3, vanilla JavaScript, Node.js built-in test runner, Codex in-app browser for visual and interaction QA.

**Spec:** `docs/superpowers/specs/2026-09-08-hardware-report-review-ui-prototype-design.md`

**2026-09-09 revision:** The approved manual-confirmation change replaces the earlier three-state-only assumption. `待人工确认` is a process state; formal output still uses the three final states.

## Global Constraints

- Formal template version is `A11`.
- Prototype viewport baseline is 1440×900; content must not horizontally scroll at 1280px width.
- Product UI uses “审核”; only the exported template-copy description retains the source word “审计”.
- Review process states are exactly: 符合、不符合、不适用、待人工确认. The pending state must be manually converted to one of the first three before completion or formal export.
- The UI must not assign issue severity or present an automatic pass/reject decision.
- Every nonconforming example must show traceable evidence.
- Missing required evidence is nonconforming and lists the missing material; any human release decision happens outside the product.
- The prototype never modifies the original report and must state this before export.
- The workspace is not currently a Git repository; implementation checkpoints are verified by tests and file inspection rather than fabricated commits.

## File Structure

- Create `prototype/a11-ui/index.html`: semantic application shell, persistent navigation, dialogs, and script/style entry points.
- Create `prototype/a11-ui/styles.css`: design tokens, desktop layouts, states, responsive behavior, and accessibility styling.
- Create `prototype/a11-ui/demo-data.js`: roles, tasks, A11 rule rows, evidence, template versions, and exported-copy summary.
- Create `prototype/a11-ui/app.js`: application state, renderers, navigation, role switching, wizard, review actions, template actions, and notifications.
- Create `prototype/a11-ui/tests/prototype.test.js`: structural and behavior-contract tests using Node.js built-ins.
- Create `prototype/a11-ui/README.md`: local preview command and two demonstration paths.

---

### Task 1: Application Shell and A11 Demo Data

**Files:**
- Create: `prototype/a11-ui/index.html`
- Create: `prototype/a11-ui/demo-data.js`
- Create: `prototype/a11-ui/app.js`
- Create: `prototype/a11-ui/styles.css`
- Test: `prototype/a11-ui/tests/prototype.test.js`

**Interfaces:**
- Produces: `window.DEMO_DATA` with `roles`, `tasks`, `rules`, and `templates` arrays.
- Produces: `window.prototypeApp` with `getState()`, `navigate(view)`, and `setRole(roleId)`.

- [ ] **Step 1: Write the failing structure test**

```javascript
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');

test('shell exposes the application landmarks and entry points', () => {
  const html = read('index.html');
  assert.match(html, /id="app-shell"/);
  assert.match(html, /id="primary-nav"/);
  assert.match(html, /id="app-main"/);
  assert.match(html, /demo-data\.js/);
  assert.match(html, /app\.js/);
});

test('A11 data contains 22 source rule rows and exactly four review states', () => {
  const source = read('demo-data.js');
  assert.equal((source.match(/ruleId:\s*['"]TR-/g) || []).length, 22);
  for (const label of ['符合', '不符合', '不适用', '待人工确认']) {
    assert.match(source, new RegExp(label));
  }
});
```

- [ ] **Step 2: Run the tests and verify failure**

Run: `node --test prototype/a11-ui/tests/prototype.test.js`  
Expected: FAIL because the prototype files do not exist.

- [ ] **Step 3: Implement the semantic shell and immutable demo-data contract**

Create the four entry files. `demo-data.js` must assign a frozen object:

```javascript
window.DEMO_DATA = Object.freeze({
  roles: [
    { id: 'tester', label: '测试报告审核' },
    { id: 'admin', label: '模板规则管理' }
  ],
  statuses: ['符合', '不符合', '不适用', '待人工确认'],
  tasks: [],
  rules: [],
  templates: []
});
```

Populate `rules` with the 22 IDs `TR-01` through `TR-22`, source sequence, title, method, requirement, evidence, and demo status. Represent `TR-05` as disabled/non-executing while keeping it visible as source sequence 5.

- [ ] **Step 4: Run the structure tests**

Run: `node --test prototype/a11-ui/tests/prototype.test.js`  
Expected: PASS for shell landmarks, 22 rules, and three statuses.

### Task 2: Workflow Dashboard, Navigation, and Role Visibility

**Files:**
- Modify: `prototype/a11-ui/app.js`
- Modify: `prototype/a11-ui/styles.css`
- Modify: `prototype/a11-ui/tests/prototype.test.js`

**Interfaces:**
- Consumes: `window.DEMO_DATA.roles`, `window.DEMO_DATA.tasks`.
- Produces: `renderSidebar(state)`, `renderDashboard(state)`, `setRole(roleId)`.

- [ ] **Step 1: Add failing navigation and permission contract tests**

```javascript
test('application declares the required views and role-gated admin navigation', () => {
  const source = read('app.js');
  for (const view of ['dashboard', 'tasks', 'create-task', 'review', 'templates', 'rule-editor']) {
    assert.match(source, new RegExp(`['"]${view}['"]`));
  }
  assert.match(source, /role\s*===\s*['"]admin['"]/);
  assert.match(source, /模板管理/);
  assert.match(source, /模板规则编辑/);
});
```

- [ ] **Step 2: Run tests and verify the new test fails**

Run: `node --test prototype/a11-ui/tests/prototype.test.js`  
Expected: FAIL because view routing and gated navigation are absent.

- [ ] **Step 3: Implement state-driven navigation and dashboard rendering**

Use one state object:

```javascript
const state = {
  role: 'tester',
  view: 'dashboard',
  selectedTaskId: 'TASK-2026-092',
  selectedRuleId: 'TR-12',
  createStep: 1,
  filters: { status: '全部', query: '' },
  notices: []
};
```

Render dashboard metrics for 待人工复核、审核处理中、本月已结束, a recent-task list, and the primary “创建审核任务” action. Re-render the sidebar after role changes; admin links must not be created for `tester`.

- [ ] **Step 4: Run tests and manually inspect default dashboard at 1440×900**

Run: `node --test prototype/a11-ui/tests/prototype.test.js`  
Expected: PASS.  
Manual: open `prototype/a11-ui/index.html`; default screen is the tester dashboard and admin links are absent.

### Task 3: Create-Task Wizard and Review Progress

**Files:**
- Modify: `prototype/a11-ui/app.js`
- Modify: `prototype/a11-ui/styles.css`
- Modify: `prototype/a11-ui/tests/prototype.test.js`

**Interfaces:**
- Consumes: active template `A11` and `state.createStep`.
- Produces: `renderCreateTask(state)`, `advanceCreateStep()`, `createDemoTask()`, `renderTaskDetail(state)`.

- [ ] **Step 1: Add failing wizard contract tests**

```javascript
test('create flow treats missing required evidence as non-compliant', () => {
  const source = read('app.js');
  for (const copy of ['选择审核模板', '上传测试报告', '上传支撑证据', '确认并创建', '缺少必需证据', '不符合']) {
    assert.match(source, new RegExp(copy));
  }
  assert.match(source, /PDF/);
  assert.match(source, /DOCX/);
  assert.match(source, /XLSX/);
  assert.match(source, /主报告.*(?:必填|不可为空)/s);
});
```

- [ ] **Step 2: Run tests and verify failure**

Run: `node --test prototype/a11-ui/tests/prototype.test.js`  
Expected: FAIL because the four-step creation flow is not implemented.

- [ ] **Step 3: Implement four creation steps and deterministic demo upload states**

The first “继续” selects A11. The report step simulates one uploaded DOCX report and enables progression only after the demo file card exists. The evidence step toggles evidence cards for JIRA、历史报告、原始记录、截图、其他附件. The confirmation step shows missing-evidence warnings but allows task creation. Creating transitions to task detail with a five-node progress timeline.

- [ ] **Step 4: Run tests and exercise the complete creation flow**

Run: `node --test prototype/a11-ui/tests/prototype.test.js`  
Expected: PASS.  
Manual: dashboard → create task → A11 → demo report → evidence → create → task detail.

### Task 4: Evidence-Centred Three-Status Review and Export

**Files:**
- Modify: `prototype/a11-ui/app.js`
- Modify: `prototype/a11-ui/styles.css`
- Modify: `prototype/a11-ui/tests/prototype.test.js`

**Interfaces:**
- Consumes: `state.selectedRuleId`, `state.filters`, `window.DEMO_DATA.rules`.
- Produces: `renderReviewWorkbench(state)`, `selectRule(ruleId)`, `applyReviewFilter(status)`, `openExportDialog()`.

- [ ] **Step 1: Add failing review invariants**

```javascript
test('review workbench preserves evidence and exposes the four review states', () => {
  const source = read('app.js');
  for (const copy of ['证据位置', '判定依据', '符合', '不符合', '不适用', '待人工确认']) {
    assert.match(source, new RegExp(copy));
  }
  assert.match(source, /不会修改原测试报告/);
  assert.match(source, /A11.*XLS/s);
  assert.doesNotMatch(source, /严重性|风险等级/);
});
```

- [ ] **Step 2: Run tests and verify failure**

Run: `node --test prototype/a11-ui/tests/prototype.test.js`  
Expected: FAIL because review actions and export dialog do not exist.

- [ ] **Step 3: Implement the three-column workbench and state transitions**

The left column renders all 22 source items with four-state filters and text search. The center column renders a realistic document preview and highlights the selected evidence excerpt. The right column renders requirement, decision basis, evidence location, and manual-resolution controls for pending items. Missing required evidence stays in the nonconforming status; supplied but inconclusive evidence becomes pending. Manual resolution records a note, reviewer, and review time, but does not create an in-product release override.

Completion and formal export are disabled while any pending item remains. Once all pending items are resolved, the export dialog summarizes the three final statuses and shows both “生成独立 A11 XLS 审核副本” and “不会修改原测试报告”. The confirm action shows a downloadable-demo success toast; it must not write or overwrite a report file.

- [ ] **Step 4: Run tests and manually verify four-state filters, pending resolution, completion gate, and final export**

Run: `node --test prototype/a11-ui/tests/prototype.test.js`  
Expected: PASS.  
Manual: choose 不符合 → select a rule → inspect the problem and evidence → open export → confirm.

### Task 5: Template Management and Rule Editor

**Files:**
- Modify: `prototype/a11-ui/app.js`
- Modify: `prototype/a11-ui/styles.css`
- Modify: `prototype/a11-ui/tests/prototype.test.js`

**Interfaces:**
- Consumes: `state.role`, templates, and 22 A11 rules.
- Produces: `renderTemplateList(state)`, `renderRuleEditor(state)`, `toggleRule(ruleId)`, `createDraftVersion()`, `publishTemplate()`.

- [ ] **Step 1: Add failing admin workflow tests**

```javascript
test('admin screens separate structural blockers from human-review warnings', () => {
  const source = read('app.js');
  for (const copy of ['上传模板', '有效校验项', '生成待发布版本', '启用', '停用', '结构校验', '需人工复核', '发布提醒']) {
    assert.match(source, new RegExp(copy));
  }
  assert.match(source, /规则编号重复/);
  assert.match(source, /缺少证据定义/);
  assert.match(source, /版本不一致/);
});
```

- [ ] **Step 2: Run tests and verify failure**

Run: `node --test prototype/a11-ui/tests/prototype.test.js`  
Expected: FAIL because template administration is absent.

- [ ] **Step 3: Implement role-gated template list and editor**

Switching to admin exposes template screens. Template list shows name, A11 version, effective item count, status, creator, and update time. Opening A11 shows source item list, rule method, evidence requirement, enabled state, structure-check panel, and a draft-version control. Rule add/delete/toggle actions affect demo state only. Duplicate rule identifiers and version mismatch remain structural blockers; missing automation criteria or evidence definition becomes a publication warning and routes the rule to manual review rather than blocking its creation.

- [ ] **Step 4: Run tests and exercise the admin path**

Run: `node --test prototype/a11-ui/tests/prototype.test.js`  
Expected: PASS.  
Manual: switch to admin → templates → A11 → generate draft → toggle a rule → inspect structure check → publish/disable demo action.

### Task 6: Visual, Responsive, and Delivery Verification

**Files:**
- Modify: `prototype/a11-ui/styles.css`
- Create: `prototype/a11-ui/README.md`
- Modify: `prototype/a11-ui/tests/prototype.test.js`

**Interfaces:**
- Consumes: all completed screens and interactions.
- Produces: verified standalone prototype and repeatable local-preview instructions.

- [ ] **Step 1: Add failing accessibility and delivery checks**

```javascript
test('delivery includes accessibility hooks and local preview instructions', () => {
  const html = read('index.html');
  const css = read('styles.css');
  const readme = read('README.md');
  assert.match(html, /lang="zh-CN"/);
  assert.match(html, /aria-live="polite"/);
  assert.match(css, /:focus-visible/);
  assert.match(css, /@media\s*\(max-width:\s*1280px\)/);
  assert.match(readme, /python.*http\.server/i);
});
```

- [ ] **Step 2: Run tests and verify failure**

Run: `node --test prototype/a11-ui/tests/prototype.test.js`  
Expected: FAIL until README and final accessibility hooks exist.

- [ ] **Step 3: Complete responsive styles and README**

Document this preview command:

```powershell
Set-Location 'E:\Coding\Hardware-Report-Review-Agent\prototype\a11-ui'
python -m http.server 8766 --bind 127.0.0.1
```

Include both demonstration paths from the approved spec. Add visible focus, text-plus-icon status labels, 14px minimum body text, minimum 36×36px primary interaction targets, and a 1280px layout adaptation without horizontal page scrolling.

- [ ] **Step 4: Run automated verification**

Run: `node --test prototype/a11-ui/tests/prototype.test.js`  
Expected: all tests PASS.

- [ ] **Step 5: Run browser QA at both required viewports**

Inspect dashboard, create flow, review workbench, export dialog, template list, and rule editor at 1440×900 and 1280×900. Verify no horizontal page scroll, no clipped primary actions, state labels include text, and both end-to-end paths remain navigable.

- [ ] **Step 6: Record the version-control limitation**

Run: `git status --short`  
Expected in the current workspace: `fatal: not a git repository`. Do not claim a commit; report this limitation with the delivered file paths.
