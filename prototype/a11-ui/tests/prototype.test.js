const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const projectRoot = path.resolve(root, '..', '..');
const readProject = file => fs.readFileSync(path.join(projectRoot, file), 'utf8');
const excludedReviewStatuses = /无法判断|接受例外/;

function bootPrototype({ transformData } = {}) {
  const elements = new Map();
  const listeners = {};
  const element = id => {
    if (!elements.has(id)) elements.set(id, { id, innerHTML: '', focus() {}, setSelectionRange() {} });
    return elements.get(id);
  };
  const context = {
    window: { setTimeout() { return 0; } },
    document: {
      getElementById: element,
      addEventListener(type, listener) { listeners[type] = listener; }
    }
  };
  vm.runInNewContext(read('demo-data.js'), context);
  if (transformData) context.window.DEMO_DATA = transformData(JSON.parse(JSON.stringify(context.window.DEMO_DATA)));
  vm.runInNewContext(read('app.js'), context);
  const clickAction = (action, dataset = {}) => listeners.click({
    target: {
      closest(selector) {
        return selector === '[data-action]' ? { dataset: { action, ...dataset } } : null;
      }
    }
  });
  const searchReview = value => listeners.input({
    target: { id: 'review-search', value, selectionStart: value.length }
  });
  return { app: context.window.prototypeApp, elements, clickAction, searchReview };
}

function bootRealPrototype(detail) {
  const elements = new Map();
  const listeners = {};
  const element = id => {
    if (!elements.has(id)) elements.set(id, { id, innerHTML: '', focus() {}, setSelectionRange() {} });
    return elements.get(id);
  };
  const context = {
    window: {
      location: { search: '' },
      setTimeout() { return 0; },
      clearTimeout() {},
      HardwareReviewApi: {
        ApiClient: class {
          async listTasks() { return { tasks: [detail] }; }
          async getTask() { return detail; }
        }
      }
    },
    document: {
      getElementById: element,
      addEventListener(type, listener) { listeners[type] = listener; }
    }
  };
  vm.runInNewContext(read('demo-data.js'), context);
  vm.runInNewContext(read('app.js'), context);
  return { app: context.window.prototypeApp, elements };
}

test('created task keeps its identity when entering review', () => {
  const { app, elements, clickAction } = bootPrototype();
  clickAction('create-demo-task');
  assert.match(elements.get('app-main').innerHTML, /TASK-2026-093/);
  app.navigate('review');
  assert.match(elements.get('app-main').innerHTML, /TASK-2026-093/);
  assert.doesNotMatch(elements.get('app-main').innerHTML, /TASK-2026-092/);
  assert.equal(app.getState().selectedTaskId, 'TASK-2026-093');
});

test('saved audit appears beside the status comparison before the editable form', () => {
  const { app, elements } = bootPrototype();
  app.selectRule('TR-01');
  app.applyManualDecision('TR-01', '不符合', '项目链接与报告不一致');
  app.navigate('review');
  const html = elements.get('app-main').innerHTML;
  const statusEnd = html.indexOf('</section>', html.indexOf('class="decision-status-grid"'));
  const auditStart = html.indexOf('class="manual-decision-record"');
  const evidenceStart = html.indexOf('class="system-evidence-section"');
  assert.ok(statusEnd < auditStart && auditStart < evidenceStart,
    'saved audit must follow the comparison before lengthy evidence and form content');
});

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
  assert.match(source, /statuses:\s*Object\.freeze\(\['符合', '不符合', '不适用', '待人工确认'\]\)/);
  assert.doesNotMatch(source, excludedReviewStatuses);
});

test('demo data freezes A11 review lifecycle, input formats, rule availability, and role capabilities', () => {
  const context = { window: {} };
  vm.runInNewContext(read('demo-data.js'), context);
  const data = JSON.parse(JSON.stringify(context.window.DEMO_DATA));
  assert.deepEqual(data.initialStatuses, ['符合', '不符合', '不适用', '待人工确认']);
  assert.deepEqual(data.finalStatuses, ['符合', '不符合', '不适用']);
  assert.deepEqual(data.supportedInputFormats, ['PDF', 'DOC', 'DOCX', 'XLS', 'XLSX']);
  assert.equal(data.rules.length, 22);
  assert.equal(data.rules.filter(rule => rule.enabled).length, 21);
  assert.equal(data.rules.find(rule => rule.ruleId === 'TR-05').enabled, false);
  const roles = data.roles;
  assert.deepEqual(roles, [
    { id: 'tester', label: '测试报告审核', canReview: true, canManageTemplates: false },
    { id: 'admin', label: '模板规则管理', canReview: false, canManageTemplates: true },
    { id: 'combined', label: '测试报告审核 + 模板规则管理', canReview: true, canManageTemplates: true }
  ]);
});

test('five formats are data-driven across upload UI', () => {
  const expectedLabel = 'PDF · DOC · DOCX · XLS · XLSX';
  const { app, elements, clickAction } = bootPrototype();
  app.navigate('create-task');
  clickAction('wizard-next');
  const html = elements.get('app-main').innerHTML;
  assert.match(html, new RegExp(`支持 ${expectedLabel}`));
  assert.equal((html.match(new RegExp(expectedLabel, 'g')) || []).length, 2);

  const custom = bootPrototype({ transformData(data) {
    data.supportedInputFormats = ['ODT', 'RTF'];
    return data;
  } });
  custom.app.navigate('create-task');
  custom.clickAction('wizard-next');
  const customHtml = custom.elements.get('app-main').innerHTML;
  assert.match(customHtml, /支持 ODT · RTF/);
  assert.equal((customHtml.match(/ODT · RTF/g) || []).length, 2);
  assert.doesNotMatch(customHtml, /PDF · DOCX · XLSX/);
});

test('frozen A11 facts preserve exact source rows, execution metadata, and TR-05 semantics', () => {
  const context = { window: {} };
  vm.runInNewContext(read('demo-data.js'), context);
  const data = context.window.DEMO_DATA;
  assert.equal(Object.isFrozen(data.initialStatuses), true);
  assert.equal(Object.isFrozen(data.finalStatuses), true);
  assert.equal(Object.isFrozen(data.supportedInputFormats), true);
  assert.deepEqual(Array.from(data.rules, rule => rule.sourceRow), [10, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33]);
  assert.equal(data.rules.some(rule => Object.hasOwn(rule, 'status')), false);

  const tr05 = data.rules.find(rule => rule.ruleId === 'TR-05');
  assert.deepEqual({
    sourceRow: tr05.sourceRow,
    method: tr05.method,
    evidence: tr05.evidence,
    initialStatus: tr05.initialStatus,
    enabled: tr05.enabled
  }, {
    sourceRow: 16,
    method: '不执行',
    evidence: '并入TR-04',
    initialStatus: '不适用',
    enabled: false
  });
  assert.equal(data.tasks.every(task => /^\d+\/21$/.test(task.progress)), true);
  const a11 = data.templates.find(template => template.version === 'A11');
  assert.equal(a11.sourceRows, 22);
  assert.equal(a11.effectiveRules, 21);
});

test('approved A11 wording distinguishes source rows from executed checks on every surface', () => {
  const context = { window: {} };
  vm.runInNewContext(read('demo-data.js'), context);
  const data = context.window.DEMO_DATA;
  assert.match(data.rules.find(rule => rule.ruleId === 'TR-03').requirement, /软件测试团队经理/);
  const tr17 = data.rules.find(rule => rule.ruleId === 'TR-17').requirement;
  for (const element of ['对象', '条件', '现象', '实际结果']) assert.match(tr17, new RegExp(element));
  const tr21 = data.rules.find(rule => rule.ruleId === 'TR-21').requirement;
  assert.match(tr21, /小结论.*页面顶端结论.*均非空/);
  assert.doesNotMatch(tr21, /一致|相符/);

  const source = read('app.js');
  assert.match(source, /const formatLabel = data\.supportedInputFormats\.join\(' · '\);/);
  assert.match(source, /const sourceRowCount = data\.rules\.length;/);
  assert.match(source, /const executedRuleCount = data\.rules\.filter\(rule => rule\.enabled\)\.length;/);
  assert.match(source, /const baselineLabel = `\$\{sourceRowCount\} 个源行 · \$\{executedRuleCount\} 个执行项`;/);
  assert.match(source, /review-summary.*\$\{executedRuleCount - pending\} \/ \$\{executedRuleCount\}/s);
  assert.doesNotMatch(source, /22 个源校验项均已执行|22 项均已执行/);

  const prototype = bootPrototype({ transformData(fixture) {
    fixture.rules.find(rule => rule.ruleId === 'TR-22').enabled = false;
    return fixture;
  } });
  prototype.app.navigate('create-task');
  assert.match(prototype.elements.get('app-main').innerHTML, /22 个源行 · 20 个执行项/);
  prototype.clickAction('wizard-next');
  prototype.clickAction('demo-upload');
  prototype.clickAction('wizard-next');
  prototype.clickAction('wizard-next');
  assert.match(prototype.elements.get('app-main').innerHTML, /22 个源行 · 20 个执行项/);
  prototype.clickAction('create-demo-task');
  let html = prototype.elements.get('app-main').innerHTML;
  assert.match(html, /22 个源行 · 20 个执行项/);
  assert.match(html, /19 \/ 20[\s\S]*已形成最终状态/);
  prototype.app.navigate('review');
  assert.match(prototype.elements.get('app-main').innerHTML, /已形成最终状态[\s\S]*19 \/ 20/);

  prototype.app.setRole('admin');
  html = prototype.elements.get('app-main').innerHTML;
  assert.match(html, /22 个源行 · 20 个执行项/);
  prototype.app.navigate('rule-editor');
  assert.match(prototype.elements.get('app-main').innerHTML, /22 个源行 · 20 个执行项/);

  for (const file of ['app.js', 'demo-data.js', 'README.md']) {
    assert.doesNotMatch(read(file), /A111|无法判断|接受例外|严重性|风险等级/, file);
  }
});

test('template mutation helpers enforce direct role permissions and structural blockers', () => {
  const { app, clickAction } = bootPrototype();
  assert.equal(app.createDraftVersion(), false);
  assert.equal(app.getState().templateDraft, false);

  app.setRole('admin');
  assert.equal(app.createDraftVersion(), true);
  app.setRole('tester');
  assert.equal(app.toggleRule('TR-01'), false);
  assert.equal(Object.hasOwn(app.getState().ruleEnabled, 'TR-01'), false);
  assert.equal(app.publishTemplate(), false);
  assert.equal(app.getState().templateDraft, true);

  app.setRole('combined');
  assert.equal(app.toggleRule('TR-01'), true);
  assert.equal(app.getState().ruleEnabled['TR-01'], false);
  clickAction('toggle-blockers');
  assert.equal(app.publishTemplate(), false);
  assert.equal(app.getState().templateDraft, true);
  clickAction('toggle-blockers');
  assert.equal(app.publishTemplate(), true);
  assert.equal(app.getState().templateDraft, false);

  const templateOnly = bootPrototype();
  templateOnly.app.setRole('admin');
  assert.equal(templateOnly.app.createDraftVersion(), true);
  assert.equal(templateOnly.app.toggleRule('TR-02'), true);
  assert.equal(templateOnly.app.publishTemplate(), true);
});

test('manual form required attributes distinguish reason from optional evidence', () => {
  const { app, elements } = bootPrototype();
  app.navigate('review');
  const html = elements.get('app-main').innerHTML;
  const reasonTag = html.match(/<textarea id="manual-review-reason"[^>]*>/)?.[0] || '';
  const evidenceTag = html.match(/<textarea id="manual-review-evidence"[^>]*>/)?.[0] || '';
  assert.match(reasonTag, /\brequired\b/);
  assert.doesNotMatch(evidenceTag, /\brequired\b/);
});

test('README documents universal override, two revisions, permissions, formats, and real/demo limits', () => {
  const readme = read('README.md');
  assert.match(readme, /任一已执行项.*系统初判.*人工/s);
  assert.match(readme, /系统初判.*符合.*TR-01.*人工最终状态.*不符合.*修改原因.*补充证据.*留空/s);
  assert.match(readme, /TR-16.*待人工确认.*最终状态/s);
  assert.match(readme, /完成第 1 次审核/);
  assert.match(readme, /D\/E\/F\/G/);
  assert.match(readme, /重新打开审核/);
  assert.match(readme, /第 2 次审核/);
  assert.match(readme, /测试报告审核.*不能.*模板/s);
  assert.match(readme, /模板规则管理.*不能.*审核结果/s);
  assert.match(readme, /组合角色.*审核流程.*模板规则/s);
  assert.match(readme, /PDF · DOC · DOCX · XLS · XLSX/);
  assert.match(readme, /默认真实模式.*上传文件.*本机服务/s);
  assert.match(readme, /\?mode=demo.*固定演示数据/s);
  assert.match(readme, /已完成审核.*下载.*A11 XLS 副本/s);
  assert.match(readme, /原报告和源模板不会被覆盖/);
  assert.doesNotMatch(readme, /XLS.*模拟.*不会生成文件/s);
});

test('navigation buttons retain accessible names when narrow CSS hides their text', () => {
  const { app, elements } = bootPrototype();
  const names = {
    dashboard: '审核工作台', tasks: '审核任务', 'create-task': '创建任务',
    templates: '模板管理', 'rule-editor': '模板规则编辑'
  };
  for (const [role, expectedViews] of [
    ['tester', ['dashboard', 'tasks', 'create-task']],
    ['admin', ['templates', 'rule-editor']],
    ['combined', ['dashboard', 'tasks', 'create-task', 'templates', 'rule-editor']]
  ]) {
    app.setRole(role);
    const buttons = [...elements.get('primary-nav').innerHTML.matchAll(/<button\b([^>]*)>/g)];
    assert.deepEqual(buttons.map(([, attrs]) => attrs.match(/data-nav="([^"]+)"/)[1]), expectedViews);
    for (const [, attrs] of buttons) {
      const view = attrs.match(/data-nav="([^"]+)"/)[1];
      assert.equal(attrs.match(/aria-label="([^"]+)"/)?.[1], names[view],
        `${role}/${view} needs an explicit accessible name independent of hidden child text`);
    }
  }
});

test('role capabilities gate review and template navigation without role-ID special cases', () => {
  const source = read('app.js');
  for (const view of ['dashboard', 'tasks', 'create-task', 'review', 'templates', 'rule-editor']) {
    assert.match(source, new RegExp(`['"]${view}['"]`));
  }
  const { app } = bootPrototype();
  for (const helper of ['currentRole', 'hasReviewPermission', 'hasTemplatePermission', 'canNavigate']) {
    assert.equal(typeof app[helper], 'function');
  }
  assert.equal(app.currentRole().id, 'tester');
  assert.equal(app.hasReviewPermission(), true);
  assert.equal(app.hasTemplatePermission(), false);
  assert.equal(app.canNavigate('review'), true);
  assert.equal(app.canNavigate('templates'), false);
  app.navigate('templates');
  assert.equal(app.getState().view, 'dashboard');

  app.setRole('admin');
  assert.equal(app.currentRole().id, 'admin');
  assert.equal(app.hasReviewPermission(), false);
  assert.equal(app.hasTemplatePermission(), true);
  assert.equal(app.getState().view, 'templates');
  app.navigate('review');
  assert.equal(app.getState().view, 'templates');

  app.setRole('combined');
  assert.equal(app.hasReviewPermission(), true);
  assert.equal(app.hasTemplatePermission(), true);
  assert.equal(app.getState().view, 'templates');
  app.navigate('review');
  assert.equal(app.getState().view, 'review');
});

test('create flow treats missing required evidence as non-compliant', () => {
  const source = read('app.js');
  const dataSource = read('demo-data.js');
  for (const copy of ['选择审核模板', '上传测试报告', '上传支撑证据', '确认并创建', '缺少必需证据', '不符合']) {
    assert.match(source, new RegExp(copy));
  }
  assert.doesNotMatch(source, excludedReviewStatuses);
  assert.match(dataSource, /supportedInputFormats: Object\.freeze\(\['PDF', 'DOC', 'DOCX', 'XLS', 'XLSX'\]\)/);
  assert.match(source, /data\.supportedInputFormats\.join\(' · '\)/);
  assert.match(source, /主报告.*(?:必填|不可为空)/s);
});

test('review workbench exposes the pending state without reintroducing excluded statuses', () => {
  const source = read('app.js');
  for (const copy of ['证据位置', '判定依据', '符合', '不符合', '不适用', '待人工确认']) {
    assert.match(source, new RegExp(copy));
  }
  assert.doesNotMatch(source, excludedReviewStatuses);
  assert.match(source, /不会修改原测试报告/);
  assert.match(source, /A11.*XLS/s);
  assert.doesNotMatch(source, /严重性|风险等级/);
});

test('dashboard and task detail derive all four result totals from review data', () => {
  const source = read('app.js');
  assert.match(source, /function renderDashboard\(\)\s*\{\s*const counts = reviewCounts\(\)/);
  assert.match(source, /function renderTaskDetail\(\)\s*\{\s*const counts = reviewCounts\(\)/);
  assert.match(source, /result-cards.*\$\{counts\['符合'\]\}.*\$\{counts\['不符合'\]\}.*\$\{counts\['不适用'\]\}.*\$\{counts\['待人工确认'\]\}/s);
});

test('all prototype surfaces and current design records include manual confirmation and exclude rejected states', () => {
  const files = [
    'prototype/a11-ui/index.html',
    'prototype/a11-ui/demo-data.js',
    'prototype/a11-ui/app.js',
    'prototype/a11-ui/README.md',
    'docs/requirements/template-field-dictionary-v0.1.md',
    'docs/requirements/template-check-rules-v0.1.md',
    'docs/superpowers/specs/2026-09-08-hardware-report-review-ui-prototype-design.md'
  ];
  const sources = files.map(file => ({ file, source: readProject(file) }));
  assert.match(sources.map(({ source }) => source).join('\n'), /待人工确认/);
  for (const { file, source } of sources) {
    assert.doesNotMatch(source, excludedReviewStatuses, file);
  }
});

test('derived review state preserves the initial status and manual status wins', () => {
  const { app } = bootPrototype();
  for (const helper of ['effectiveRule', 'reviewRules', 'pendingReviewCount', 'reviewCounts']) {
    assert.equal(typeof app[helper], 'function');
  }
  assert.equal(app.reviewRules().length, 21);
  assert.equal(app.reviewRules().some(rule => rule.ruleId === 'TR-05'), false);
  const implicit = app.effectiveRule(app.reviewRules().find(rule => rule.ruleId === 'TR-01'));
  assert.equal(implicit.initialStatus, '符合');
  assert.equal(implicit.finalStatus, '符合');
  assert.equal(implicit.displayStatus, '符合');
  assert.equal(implicit.manualReview, null);
  const pending = app.effectiveRule(app.reviewRules().find(rule => rule.ruleId === 'TR-16'));
  assert.equal(pending.initialStatus, '待人工确认');
  assert.equal(pending.finalStatus, null);
  assert.equal(pending.displayStatus, '待人工确认');
  assert.equal(pending.manualReview, null);
  assert.equal(app.pendingReviewCount(), 1);

  assert.equal(app.applyManualDecision('TR-01', '不符合', '复核后发现数据不一致。'), true);
  const overridden = app.reviewRules().find(rule => rule.ruleId === 'TR-01');
  assert.equal(overridden.initialStatus, '符合');
  assert.equal(overridden.finalStatus, '不符合');
  assert.equal(overridden.displayStatus, '不符合');
  assert.equal(overridden.manualReview.status, '不符合');
  assert.equal(app.reviewCounts()['符合'], 10);
  assert.equal(app.reviewCounts()['不符合'], 8);
});

test('review permission can change any enabled initial state without replacing its source status', () => {
  const { app } = bootPrototype();
  const cases = [
    ['TR-01', '符合', '不符合'],
    ['TR-02', '不符合', '不适用'],
    ['TR-06', '不适用', '符合'],
    ['TR-16', '待人工确认', '符合']
  ];

  for (const [ruleId, initialStatus, finalStatus] of cases) {
    assert.equal(app.applyManualDecision(ruleId, finalStatus, `人工复核 ${ruleId}`), true);
    const reviewed = app.reviewRules().find(rule => rule.ruleId === ruleId);
    assert.equal(reviewed.initialStatus, initialStatus);
    assert.equal(reviewed.finalStatus, finalStatus);
    assert.equal(reviewed.displayStatus, finalStatus);
  }
});

test('every executed result renders initial and final status plus one stable manual-decision form', () => {
  const { app, elements, clickAction } = bootPrototype();
  app.navigate('review');

  for (const rule of app.reviewRules()) {
    app.selectRule(rule.ruleId);
    const html = elements.get('app-main').innerHTML;
    assert.match(html, /系统初判/);
    assert.match(html, new RegExp(`系统初判[\\s\\S]*${rule.initialStatus}`));
    assert.match(html, /人工最终状态/);
    assert.match(html, /<form class="manual-decision-form">/);
    assert.match(html, /id="manual-final-status"/);
    assert.match(html, /id="manual-review-reason"/);
    assert.match(html, /修改原因[\s\S]*必填/);
    assert.match(html, /id="manual-review-evidence"/);
    assert.match(html, /补充证据[\s\S]*选填/);
    assert.equal((html.match(/data-action="save-manual-decision"/g) || []).length, 1);
    assert.doesNotMatch(html, /data-action="resolve-review"/);
  }

  app.selectRule('TR-01');
  elements.set('manual-final-status', { value: '不符合' });
  elements.set('manual-review-reason', { value: '复核发现数据不一致。' });
  elements.set('manual-review-evidence', { value: '报告第 8 页' });
  clickAction('save-manual-decision');

  const reviews = app.getState().manualReviews;
  assert.equal(reviews['TR-01']?.status, '不符合');
  assert.equal(reviews['TR-01']?.reason, '复核发现数据不一致。');
  assert.equal(reviews['TR-01']?.supplementalEvidence, '报告第 8 页');
  const savedHtml = elements.get('app-main').innerHTML;
  assert.match(savedHtml, /class="manual-decision-record"/);
  assert.match(savedHtml, /复核人[\s\S]*陈工/);
  assert.match(savedHtml, /复核时间[\s\S]*今天 17:18/);
  assert.match(savedHtml, /修改原因[\s\S]*复核发现数据不一致。/);
  assert.match(savedHtml, /补充证据[\s\S]*报告第 8 页/);
});

test('evidence-address source row stays visible, non-executed, and cannot receive a manual decision', () => {
  const { app, elements, clickAction } = bootPrototype();
  app.navigate('review');

  let html = elements.get('app-main').innerHTML;
  assert.equal((html.match(/data-rule="TR-/g) || []).length, 22);
  assert.match(html, /已形成最终状态[\s\S]*\/ 21/);
  assert.match(html, /22 个源行 · 21 个执行项/);

  app.selectRule('TR-05');
  html = elements.get('app-main').innerHTML;
  assert.equal(app.getState().selectedRuleId, 'TR-05');
  assert.match(html, /class="rule-row source-row-disabled is-selected"/);
  assert.match(html, /TR-05 · 证据地址 · 不独立执行/);
  assert.match(html, /证据地址 · 不独立执行/);
  assert.doesNotMatch(html, /id="manual-final-status"/);
  assert.doesNotMatch(html, /id="manual-review-reason"/);
  assert.doesNotMatch(html, /id="manual-review-evidence"/);
  assert.doesNotMatch(html, /data-action="save-manual-decision"/);

  elements.set('manual-final-status', { value: '符合' });
  elements.set('manual-review-reason', { value: '停用项不应复核。' });
  elements.set('manual-review-evidence', { value: '不应保存' });
  clickAction('save-manual-decision');
  assert.equal(app.getState().manualReviews['TR-05'], undefined);
});

test('TR-05 detail presents evidence-address semantics without independent result cards', () => {
  const { app, elements } = bootPrototype();
  app.navigate('review');
  app.selectRule('TR-05');
  const html = elements.get('app-main').innerHTML;
  const detail = html.slice(html.indexOf('<aside class="decision-panel">'));
  assert.match(detail, /TR-05 · 源序号 5/);
  assert.match(detail, /证据地址 · 不独立执行/);
  assert.match(detail, /该源行并入 TR-04 作为证据地址/);
  assert.doesNotMatch(detail, /系统初判|人工最终状态|decision-status-grid|result-status/);
  assert.doesNotMatch(detail, /manual-decision-form/);
  assert.match(html, /data-rule="TR-05"/);
  assert.equal((html.match(/data-rule="TR-/g) || []).length, 22);
});

test('status filters show only executed results while all-source search retains TR-05', () => {
  const { app, elements, searchReview } = bootPrototype();
  const visibleIds = () => [...elements.get('app-main').innerHTML.matchAll(/data-rule="(TR-\d+)"/g)].map(match => match[1]);
  app.navigate('review');
  app.selectRule('TR-05');
  app.applyReviewFilter('不适用');
  assert.deepEqual(visibleIds(), ['TR-06', 'TR-19']);
  assert.equal(app.getState().selectedRuleId, 'TR-06');
  assert.match(elements.get('app-main').innerHTML, />不适用 2<\/button>/);

  searchReview('  tr-19  ');
  assert.deepEqual(visibleIds(), ['TR-19']);
  assert.equal(app.getState().selectedRuleId, 'TR-06', 'search preserves the current labelled detail');
  app.selectRule('TR-19');
  searchReview('共享路径');
  assert.deepEqual(visibleIds(), []);
  assert.equal(app.getState().selectedRuleId, 'TR-19', 'empty search does not change the saved target');
  app.applyReviewFilter('全部');
  assert.deepEqual(visibleIds(), ['TR-05']);
  assert.equal(app.getState().selectedRuleId, 'TR-05');
  searchReview('');
  assert.equal(visibleIds().length, 22);
  assert.ok(visibleIds().includes('TR-05'));
});

test('pending review cannot finish or export until a reviewer records a final status and reason', () => {
  const { app, elements } = bootPrototype();
  assert.equal(app.pendingReviewCount(), 1);
  assert.equal(app.reviewCounts()['待人工确认'], 1);
  assert.equal(app.canFinalizeReview(), false);
  app.navigate('review');
  assert.match(elements.get('app-main').innerHTML, /data-action="finish-review"[^>]*disabled/);
  assert.doesNotMatch(elements.get('app-main').innerHTML, /data-action="open-export"/);

  assert.equal(app.applyManualDecision('TR-16', '符合', ''), false);
  assert.equal(app.applyManualDecision('TR-16', '符合', '已人工核对问题排列依据。'), true);
  assert.equal(app.pendingReviewCount(), 0);
  assert.equal(app.reviewCounts()['待人工确认'], 0);
  assert.equal(app.canFinalizeReview(), true);
  const review = app.getState().manualReviews['TR-16'];
  assert.equal(review.status, '符合');
  assert.equal(review.reason, '已人工核对问题排列依据。');
  assert.equal(review.supplementalEvidence, '');
  assert.equal(review.reviewer, '陈工');
  assert.equal(review.reviewedAt, '今天 17:18');
});

test('manual decisions enforce permissions, task state, enabled rules, reasons, and data-defined targets', () => {
  const { app, clickAction } = bootPrototype();
  assert.equal(app.applyManualDecision('TR-16', '待人工确认', '仍不能判断'), false);
  assert.equal(app.applyManualDecision('TR-16', '接受例外', '环境限制'), false);
  assert.equal(app.applyManualDecision('TR-05', '符合', '停用项不应复核'), false);
  assert.equal(app.applyManualDecision('TR-01', '不符合', '   '), false);
  assert.equal(app.reviewCounts()['待人工确认'], 1);

  app.setRole('admin');
  assert.equal(app.applyManualDecision('TR-01', '不符合', '管理员无审核权限'), false);
  app.setRole('combined');
  assert.equal(app.applyManualDecision('TR-01', '不符合', '联合角色人工复核', '报告第 8 页'), true);
  assert.equal(app.getState().manualReviews['TR-01'].supplementalEvidence, '报告第 8 页');

  assert.equal(app.applyManualDecision('TR-16', '符合', '完成最后待确认项'), true);
  clickAction('finish-review');
  assert.equal(app.getState().taskCompleted, true);
  assert.equal(app.applyManualDecision('TR-02', '符合', '结束后不得改判'), false);
});

test('manual decision targets come from DEMO_DATA.finalStatuses', () => {
  const { app } = bootPrototype({
    transformData(data) {
      data.finalStatuses = ['符合'];
      return data;
    }
  });
  assert.equal(app.applyManualDecision('TR-01', '不符合', '不在该数据集允许范围'), false);
  assert.equal(app.applyManualDecision('TR-01', '符合', '数据集允许此结论'), true);
});

test('completion accepts only resolved reviews and captures an independent 21-rule snapshot', () => {
  const { app } = bootPrototype();
  assert.equal(typeof app.completeReview, 'function');
  assert.equal(app.getState().reviewRevision, 1);
  assert.equal(app.getState().completedRevisions.length, 0);
  assert.equal(app.completeReview(), false);
  assert.equal(app.getState().taskCompleted, false);
  assert.equal(app.getState().completedRevisions.length, 0);

  app.applyManualDecision('TR-16', '符合', '已核对排序依据。');
  const liveReview = app.reviewRules().find(rule => rule.ruleId === 'TR-16').manualReview;
  assert.equal(app.completeReview(), true);
  assert.equal(app.getState().taskCompleted, true);
  assert.equal(app.completeReview(), false);
  const completed = app.getState().completedRevisions;
  assert.equal(completed.length, 1);
  assert.equal(completed[0].revision, 1);
  assert.equal(completed[0].completedBy, '陈工');
  assert.equal(completed[0].completedAt, '今天 17:24');
  assert.equal(completed[0].rules.length, 21);
  assert.equal(completed[0].rules.some(rule => rule.ruleId === 'TR-05'), false);
  const plain = value => JSON.parse(JSON.stringify(value));
  assert.deepEqual(plain(completed[0].rules.find(rule => rule.ruleId === 'TR-01')), {
    ruleId: 'TR-01', initialStatus: '符合', finalStatus: '符合', manualReview: null
  });
  assert.deepEqual(plain(completed[0].rules.find(rule => rule.ruleId === 'TR-16')), {
    ruleId: 'TR-16', initialStatus: '待人工确认', finalStatus: '符合',
    manualReview: { status: '符合', reason: '已核对排序依据。', supplementalEvidence: '', reviewer: '陈工', reviewedAt: '今天 17:18' }
  });
  liveReview.reason = '外部引用变化';
  completed[0].rules[0].finalStatus = '不符合';
  assert.equal(app.getState().completedRevisions[0].rules.find(rule => rule.ruleId === 'TR-16').manualReview.reason, '已核对排序依据。');
  assert.equal(app.getState().completedRevisions[0].rules[0].finalStatus, '符合');
});

test('reopen keeps the completed revision and manual decisions while a new revision changes', () => {
  const { app, elements, clickAction } = bootPrototype();
  assert.equal(typeof app.reopenReview, 'function');
  app.navigate('review');
  assert.equal(app.reopenReview(), false);
  app.applyManualDecision('TR-16', '符合', '第一次复核');
  clickAction('finish-review');
  const first = JSON.stringify(app.getState().completedRevisions[0]);
  assert.match(elements.get('app-main').innerHTML, /data-action="reopen-review"/);
  clickAction('reopen-review');
  assert.equal(app.getState().taskCompleted, false);
  assert.equal(app.getState().reviewRevision, 2);
  assert.equal(app.getState().manualReviews['TR-16'].reason, '第一次复核');
  assert.equal(app.getState().completedRevisions.length, 1);
  assert.equal(app.canExportReview(), false);
  assert.match(elements.get('app-main').innerHTML, /id="manual-final-status"/);
  assert.equal(app.reopenReview(), false);
  assert.equal(app.getState().reviewRevision, 2);
  assert.equal(app.applyManualDecision('TR-16', '不符合', '第二次复核'), true);
  assert.equal(app.completeReview(), true);
  assert.equal(app.getState().completedRevisions.length, 2);
  assert.equal(JSON.stringify(app.getState().completedRevisions[0]), first);
  assert.equal(app.getState().completedRevisions[1].revision, 2);
  assert.equal(app.getState().completedRevisions[1].rules.find(rule => rule.ruleId === 'TR-16').finalStatus, '不符合');
});

test('completion accepts tester and combined permissions but blocks direct admin lifecycle calls', () => {
  const { app, clickAction } = bootPrototype();
  assert.equal(typeof app.completeReview, 'function');
  app.applyManualDecision('TR-16', '符合', '人工确认');
  app.setRole('admin');
  assert.equal(app.completeReview(), false);
  clickAction('finish-review');
  assert.equal(app.getState().taskCompleted, false);
  assert.equal(app.getState().completedRevisions.length, 0);
  app.setRole('tester');
  assert.equal(app.completeReview(), true);
  assert.equal(app.canExportReview(), true);
  app.setRole('admin');
  assert.equal(app.reopenReview(), false);
  clickAction('reopen-review');
  assert.equal(app.getState().taskCompleted, true);
  assert.equal(app.getState().reviewRevision, 1);
  assert.equal(app.canExportReview(), false);
  assert.equal(app.buildExportRows().length, 0);
  assert.equal(app.openExportDialog(), false);
  app.setRole('combined');
  assert.equal(app.canExportReview(), true);
  assert.equal(app.reopenReview(), true);
  assert.equal(app.completeReview(), true);
  assert.equal(app.canExportReview(), true);
});

test('export rows use final statuses, system basis and manual reason for enabled rules only', () => {
  const { app } = bootPrototype();
  assert.equal(typeof app.buildExportRows, 'function');
  app.applyManualDecision('TR-16', '符合', '顺序已核对');
  app.applyManualDecision('TR-01', '不符合', '链接与项目不一致', '补充截图');
  app.completeReview();
  const rows = JSON.parse(JSON.stringify(app.buildExportRows()));
  assert.equal(rows.length, 21);
  assert.equal(rows.some(row => row.ruleId === 'TR-05'), false);
  assert.deepEqual(rows.find(row => row.ruleId === 'TR-01'), {
    ruleId: 'TR-01', D: '', E: '╳', F: '', G: 'JIRA项目页面截图、报告第1页；链接与项目不一致'
  });
  assert.deepEqual(rows.find(row => row.ruleId === 'TR-04'), {
    ruleId: 'TR-04', D: '√', E: '', F: '', G: '报告第12页、功耗记录截图'
  });
  assert.deepEqual(rows.find(row => row.ruleId === 'TR-06'), {
    ruleId: 'TR-06', D: '', E: '', F: '⊙', G: '测试需求清单、委外安排证明'
  });
  assert.deepEqual(rows.find(row => row.ruleId === 'TR-02'), {
    ruleId: 'TR-02', D: '', E: '╳', F: '', G: '上阶段问题清单、回归测试记录；缺少必需证据：未提供上阶段问题清单和回归测试记录。'
  });
  assert.equal(rows.find(row => row.ruleId === 'TR-16').G, '报告第28—29页；材料已提供，但模板未定义问题排序依据，规则与AI均不能形成有证据支持的明确结论。；顺序已核对');
});

test('export requires completion even after all pending decisions have been resolved', () => {
  const { app, elements, clickAction } = bootPrototype();
  assert.equal(typeof app.canExportReview, 'function');
  app.navigate('review');
  assert.equal(app.canExportReview(), false);
  assert.equal(app.buildExportRows().length, 0);
  assert.equal(app.openExportDialog(), false);
  assert.match(elements.get('app-main').innerHTML, /data-action="finish-review"[^>]*disabled/);
  assert.match(elements.get('app-main').innerHTML, /仍有 1 项待人工复核/);
  assert.doesNotMatch(elements.get('app-main').innerHTML, /data-action="open-export"/);
  app.applyManualDecision('TR-16', '符合', '人工确认');
  assert.equal(app.openExportDialog(), false);
  assert.equal(app.buildExportRows().length, 0);
  assert.match(elements.get('app-main').innerHTML, /data-action="finish-review"[^>]*>完成审核/);
  assert.doesNotMatch(elements.get('app-main').innerHTML, /data-action="open-export"/);
  clickAction('finish-review');
  assert.equal(app.getState().completedRevisions.length, 1);
  assert.equal(app.canExportReview(), true);
  const html = elements.get('app-main').innerHTML;
  assert.match(html, /data-action="open-export"[^>]*>导出正式审核副本/);
  assert.match(html, /data-action="reopen-review"[^>]*>重新打开审核/);
  assert.doesNotMatch(html, /data-action="finish-review"|manual-decision-form/);
  assert.equal(app.openExportDialog(), true);
  const dialog = elements.get('dialog-root').innerHTML;
  assert.match(dialog, /原型预览/);
  assert.match(dialog, /D\/E\/F.*最终状态/);
  assert.match(dialog, /G.*系统.*人工.*原因/);
  clickAction('confirm-export');
  assert.equal(elements.get('dialog-root').innerHTML, '');
  assert.match(elements.get('toast-region').innerHTML, /原型.*未.*文件/);
});

test('completion accepts detached manual review results without allowing pre-completion mutation', () => {
  const { app } = bootPrototype();
  app.applyManualDecision('TR-16', '符合', '已核实排序');
  const listed = app.reviewRules().find(rule => rule.ruleId === 'TR-16');
  listed.manualReview.status = '接受例外';
  listed.manualReview.reason = '';
  const effective = app.effectiveRule(listed);
  assert.equal(effective.finalStatus, '符合');
  effective.manualReview.status = '待人工确认';
  effective.manualReview.reason = '被外部改写';
  assert.equal(app.getState().manualReviews['TR-16'].status, '符合');
  assert.equal(app.getState().manualReviews['TR-16'].reason, '已核实排序');
  assert.equal(app.completeReview(), true);
  const saved = app.getState().completedRevisions[0].rules.find(rule => rule.ruleId === 'TR-16');
  assert.equal(saved.finalStatus, '符合');
  assert.equal(saved.manualReview.reason, '已核实排序');
  assert.equal(app.buildExportRows().find(row => row.ruleId === 'TR-16').D, '√');
});

test('export rows resist returned manual review mutation after completion', () => {
  const { app } = bootPrototype();
  app.applyManualDecision('TR-16', '符合', '完成时依据');
  assert.equal(app.completeReview(), true);
  const before = JSON.stringify(app.buildExportRows());
  const listed = app.reviewRules().find(rule => rule.ruleId === 'TR-16');
  const effective = app.effectiveRule(listed);
  listed.manualReview.status = '接受例外';
  listed.manualReview.reason = '改写后的原因';
  effective.manualReview.status = '不适用';
  effective.manualReview.reason = '另一个改写';
  assert.equal(app.getState().manualReviews['TR-16'].status, '符合');
  assert.equal(app.getState().manualReviews['TR-16'].reason, '完成时依据');
  assert.equal(JSON.stringify(app.buildExportRows()), before);
  assert.equal(app.getState().completedRevisions[0].rules.find(rule => rule.ruleId === 'TR-16').finalStatus, '符合');
});

test('completion accepts no enabled result outside the data-defined final states', () => {
  const { app } = bootPrototype({ transformData(data) {
    data.rules.find(rule => rule.ruleId === 'TR-01').initialStatus = '接受例外';
    return data;
  } });
  app.applyManualDecision('TR-16', '符合', '解决待确认项');
  assert.equal(app.pendingReviewCount(), 0);
  assert.equal(app.completeReview(), false);
  assert.equal(app.getState().taskCompleted, false);
  assert.equal(app.getState().completedRevisions.length, 0);
  assert.equal(app.buildExportRows().length, 0);
});

test('export rows use the latest completed snapshot instead of current result derivation', () => {
  let fixture;
  const { app } = bootPrototype({ transformData(data) { fixture = data; return data; } });
  app.applyManualDecision('TR-16', '符合', '第一版依据');
  app.completeReview();
  fixture.rules.find(rule => rule.ruleId === 'TR-01').initialStatus = '不适用';
  fixture.rules.find(rule => rule.ruleId === 'TR-01').evidence = '完成后改变的系统证据';
  fixture.rules.find(rule => rule.ruleId === 'TR-01').finding = '完成后改变的判定依据';
  assert.equal(app.reviewRules().find(rule => rule.ruleId === 'TR-01').finalStatus, '不适用');
  assert.equal(app.buildExportRows().find(row => row.ruleId === 'TR-01').D, '√');
  assert.equal(app.buildExportRows().find(row => row.ruleId === 'TR-01').G, 'JIRA项目页面截图、报告第1页');
  app.reopenReview();
  app.applyManualDecision('TR-16', '不符合', '第二版依据');
  app.completeReview();
  const rows = app.buildExportRows();
  assert.equal(rows.length, 21);
  assert.equal(rows.find(row => row.ruleId === 'TR-01').F, '⊙');
  assert.equal(rows.find(row => row.ruleId === 'TR-16').E, '╳');
  assert.match(rows.find(row => row.ruleId === 'TR-16').G, /；第二版依据$/);
});

test('export rows reject a snapshot with a final state no longer allowed by the data', () => {
  let fixture;
  const { app } = bootPrototype({ transformData(data) { fixture = data; return data; } });
  app.applyManualDecision('TR-16', '符合', '已核实');
  app.completeReview();
  fixture.finalStatuses = ['符合', '不符合'];
  assert.equal(app.buildExportRows().length, 0);
});

test('admin screens keep structural blockers but warn instead of blocking human-review rules', () => {
  const source = read('app.js');
  for (const copy of ['上传模板', '有效校验项', '生成待发布版本', '启用', '停用', '结构校验', '需人工复核', '发布提醒']) {
    assert.match(source, new RegExp(copy));
  }
  assert.match(source, /规则编号重复/);
  assert.match(source, /版本不一致/);
  assert.match(source, /缺少证据定义.*待人工确认/s);
  assert.doesNotMatch(source, /缺少证据定义.*修正以下.*才能发布/s);
  assert.match(source, /data-action="publish-template"[^>]*state\.publishBlocked[^>]*disabled/);
});

test('delivery includes accessibility hooks and local preview instructions', () => {
  const html = read('index.html');
  const css = read('styles.css');
  const readme = read('README.md');
  assert.match(html, /lang="zh-CN"/);
  assert.match(html, /aria-live="polite"/);
  assert.match(css, /:focus-visible/);
  assert.match(css, /@media\s*\(max-width:\s*1280px\)/);
  assert.match(readme, /uvicorn.*127\.0\.0\.1.*8766/i);
});

test('narrow browser panels collapse navigation and content to one column', () => {
  const css = read('styles.css');
  assert.match(css, /@media\s*\(max-width:\s*760px\)/);
  assert.match(css, /grid-template-columns:\s*74px\s+minmax\(0,\s*1fr\)/);
  assert.match(css, /\.metric-grid\s*\{\s*grid-template-columns:\s*1fr/);
  assert.match(css, /\.review-workbench\s*\{\s*grid-template-columns:\s*1fr/);
  assert.match(css, /\.decision-status-grid\s*\{\s*grid-template-columns:\s*1fr/);
});

test('template editor header renders the resolved version label', () => {
  const source = read('app.js');
  assert.doesNotMatch(source, /当前版本 \$\{version\}[^`]/);
  assert.match(source, /当前版本 \$\{version\}`/);
});

test('real API client loads before the application and demo mode is explicit', () => {
  const html = read('index.html');
  const apiIndex = html.indexOf('api-client.js');
  const appIndex = html.indexOf('app.js');
  assert.ok(apiIndex >= 0 && apiIndex < appIndex, 'api-client.js must load before app.js');
  assert.match(read('app.js'), /mode.*demo|demo.*mode/i);
});

test('API client creates aligned multipart uploads without inventing task data', async () => {
  class FakeFormData {
    constructor() { this.entries = []; }
    append(name, value) { this.entries.push([name, value]); }
  }
  const calls = [];
  const context = {
    window: {
      FormData: FakeFormData,
      fetch: async (url, options = {}) => {
        calls.push({ url, options });
        return { ok: true, status: 201, async json() { return { id: 'server-task-id' }; } };
      }
    }
  };
  vm.runInNewContext(read('api-client.js'), context);
  const client = new context.window.HardwareReviewApi.ApiClient();
  const primary = { name: 'report.xls' };
  const support = { name: 'jira.pdf' };
  const result = await client.createTask({
    templateId: 'template-a11',
    primaryReport: primary,
    supportingFiles: [{ file: support, evidenceKinds: ['JIRA_RECORD', 'OTHER'] }]
  });
  assert.equal(result.id, 'server-task-id');
  assert.equal(calls[0].url, '/api/tasks');
  assert.equal(calls[0].options.method, 'POST');
  assert.deepEqual(calls[0].options.body.entries.slice(0, 3), [
    ['template_id', 'template-a11'], ['primary_report', primary], ['supporting_files', support]
  ]);
  assert.deepEqual(JSON.parse(calls[0].options.body.entries[3][1]), [
    { evidence_kinds: ['JIRA_RECORD', 'OTHER'] }
  ]);
});

test('real create flow selects only published templates and submits the frozen version id', () => {
  const source = read('app.js');
  assert.match(source, /status === 'PUBLISHED'/);
  assert.match(source, /data-action="select-real-template"/);
  assert.match(source, /templateId:\s*state\.createTemplateId/);
  assert.match(source, /任务创建后.*模板.*不影响|冻结/);
});

test('API client exposes the seven frozen task operations', async () => {
  const calls = [];
  const context = {
    window: {
      FormData: class { append() {} },
      fetch: async (url, options = {}) => {
        calls.push([url, options.method || 'GET', options.body || null]);
        return { ok: true, status: 200, async json() { return {}; } };
      }
    }
  };
  vm.runInNewContext(read('api-client.js'), context);
  const client = new context.window.HardwareReviewApi.ApiClient();
  await client.executeTask('task-1');
  await client.listTasks();
  await client.getTask('task-1');
  await client.saveManualDecision('task-1', 'TR-01', { finalStatus: 'COMPLIANT', reason: 'checked' });
  await client.completeTask('task-1');
  await client.reopenTask('task-1');
  assert.deepEqual(calls.map(([url, method]) => [url, method]), [
    ['/api/tasks/task-1/execute', 'POST'],
    ['/api/tasks', 'GET'],
    ['/api/tasks/task-1', 'GET'],
    ['/api/tasks/task-1/rules/TR-01/manual-decision', 'PUT'],
    ['/api/tasks/task-1/complete', 'POST'],
    ['/api/tasks/task-1/reopen', 'POST']
  ]);
  assert.deepEqual(JSON.parse(calls[3][2]), {
    final_status: 'COMPLIANT', reason: 'checked', supplemental_evidence: []
  });
});

test('API client exposes persisted template upload and lifecycle operations', async () => {
  class FakeFormData {
    constructor() { this.entries = []; }
    append(name, value) { this.entries.push([name, value]); }
  }
  const calls = [];
  const context = {
    window: {
      FormData: FakeFormData,
      fetch: async (url, options = {}) => {
        calls.push([url, options.method || 'GET', options.body || null]);
        return { ok: true, status: options.method === 'DELETE' ? 204 : 200, async json() { return {}; } };
      }
    }
  };
  vm.runInNewContext(read('api-client.js'), context);
  const client = new context.window.HardwareReviewApi.ApiClient();
  const source = { name: 'A12.xls' };

  await client.listTemplates();
  await client.uploadTemplate({ source, name: '硬件测试过程检查单', version: 'A12', actor: '模板管理员' });
  await client.getTemplate('template-1');
  await client.updateTemplateRule('template-1', 'TR-01', { summary: '新名称' });
  await client.addTemplateRule('template-1', { rule_id: 'CUSTOM-01' });
  await client.deleteTemplateRule('template-1', 'CUSTOM-01');
  await client.publishTemplate('template-1');
  await client.retireTemplate('template-1');

  assert.deepEqual(calls.map(([url, method]) => [url, method]), [
    ['/api/templates', 'GET'],
    ['/api/templates', 'POST'],
    ['/api/templates/template-1', 'GET'],
    ['/api/templates/template-1/rules/TR-01', 'PUT'],
    ['/api/templates/template-1/rules', 'POST'],
    ['/api/templates/template-1/rules/CUSTOM-01', 'DELETE'],
    ['/api/templates/template-1/publish', 'POST'],
    ['/api/templates/template-1/retire', 'POST']
  ]);
  assert.deepEqual(calls[1][2].entries, [
    ['source', source], ['name', '硬件测试过程检查单'], ['version', 'A12'], ['actor', '模板管理员']
  ]);
});

test('real template administration renders persisted versions and draft rules', async () => {
  const elements = new Map();
  const listeners = {};
  const element = id => {
    if (!elements.has(id)) elements.set(id, { id, innerHTML: '', focus() {}, setSelectionRange() {} });
    return elements.get(id);
  };
  const templates = [
    {
      id: 'tpl-a12', name: '硬件测试过程检查单', version: 'A12', status: 'DRAFT',
      effective_rules: 20, source_rows: 22, created_by: '模板管理员', updated_at: '2026-09-17T08:00:00Z',
      validation_findings: [{ code: 'SEMANTIC_REVIEW_CONFIGURATION_REQUIRED', severity: 'WARNING', message: '语义项需要配置' }]
    },
    {
      id: 'tpl-a11', name: '硬件测试过程检查单', version: 'A11', status: 'PUBLISHED',
      effective_rules: 21, source_rows: 22, created_by: '系统基线', updated_at: '2026-09-17T07:00:00Z', validation_findings: []
    }
  ];
  const detail = {
    template: templates[0],
    rules: [{
      id: 'rule-1', template_id: 'tpl-a12', rule_id: 'TR-01', source_row: 10, source_sequence: 1,
      summary: 'JIRA项目及链接', verifiable_requirement: '报告包含对应链接', required_materials: 'JIRA页面截图',
      main_judgment: 'RULE', confirmed_boundary: '缺失材料时不符合', enabled: true
    }]
  };
  const context = {
    window: {
      location: { search: '' }, setTimeout() { return 0; }, clearTimeout() {},
      HardwareReviewApi: { ApiClient: class {
        async listTasks() { return { tasks: [] }; }
        async listTemplates() { return { templates }; }
        async getTemplate() { return detail; }
      } }
    },
    document: {
      getElementById: element,
      addEventListener(type, listener) { listeners[type] = listener; }
    }
  };
  vm.runInNewContext(read('demo-data.js'), context);
  vm.runInNewContext(read('app.js'), context);
  const app = context.window.prototypeApp;

  app.setRole('admin');
  await app.refreshRealTemplates();
  app.navigate('templates');
  let html = elements.get('app-main').innerHTML;
  assert.match(html, /A12/);
  assert.match(html, /待发布/);
  assert.match(html, /系统基线/);
  assert.doesNotMatch(html, /模板管理模拟/);

  await app.openRealTemplate('tpl-a12');
  html = elements.get('app-main').innerHTML;
  assert.match(html, /JIRA项目及链接/);
  assert.match(html, /语义项需要配置/);
  assert.match(html, /发布版本/);
  assert.doesNotMatch(html, /模板规则模拟/);
});

test('failed real task identifies the failed material and offers a valid recovery action', async () => {
  const detail = {
    id: 'task-failed', display_name: 'primary.xls', template_version: 'A11', state: 'FAILED',
    updated_at: '2026-09-16T00:00:00Z', rule_results: [], manual_decisions: [], revisions: [],
    source_files: [
      { id: 'primary', role: 'PRIMARY_REPORT', original_name: 'primary.xls', detected_format: 'XLS', size_bytes: 10, evidence_kinds: [] },
      { id: 'support', role: 'SUPPORTING_EVIDENCE', original_name: 'support.doc', detected_format: 'DOC', size_bytes: 20, evidence_kinds: ['OTHER'] }
    ],
    stage_failures: [
      { stage: 'PARSING', code: 'DOC_CONVERSION_FAILED', message: 'Microsoft Word COM server is unavailable' }
    ]
  };
  const { app, elements } = bootRealPrototype(detail);

  await app.openRealTask(detail.id);
  const html = elements.get('app-main').innerHTML;

  assert.match(html, /材料解析失败 · PARSING/);
  assert.match(html, /support\.doc: Microsoft Word COM server is unavailable/);
  assert.match(html, /data-nav="create-task"[^>]*>重新上传材料/);
  assert.doesNotMatch(html, /retry-real-task|primary\.xls · PARSING/);

  app.navigate('create-task');
  assert.match(elements.get('app-main').innerHTML, /DOC\/DOCX 依赖本机 Microsoft Word；WPS 不作为兼容依据/);
});

test('completed real task exposes the checklist download in task detail and review', async () => {
  const detail = {
    id: 'task-completed', display_name: 'completed.xls', template_version: 'A11', state: 'COMPLETED',
    updated_at: '2026-09-17T00:00:00Z', rule_results: [], manual_decisions: [], revisions: [{ revision_no: 1 }],
    source_files: [], stage_failures: []
  };
  const { app, elements } = bootRealPrototype(detail);

  await app.openRealTask(detail.id, 'tasks');

  let html = elements.get('app-main').innerHTML;
  assert.match(html, /href="\/api\/tasks\/task-completed\/export"/);
  assert.match(html, />导出测试检查表<\/a>/);
  app.navigate('review');
  html = elements.get('app-main').innerHTML;
  assert.match(html, /href="\/api\/tasks\/task-completed\/export"/);
  assert.match(html, /data-action="reopen-real-task"/);
});

test('real task hides the checklist download until audit completion', async () => {
  const detail = {
    id: 'task-ready', display_name: 'ready.xls', template_version: 'A11', state: 'READY_FOR_REVIEW',
    updated_at: '2026-09-17T00:00:00Z', rule_results: [], manual_decisions: [], revisions: [],
    source_files: [], stage_failures: []
  };
  const { app, elements } = bootRealPrototype(detail);

  await app.openRealTask(detail.id, 'tasks');

  assert.doesNotMatch(elements.get('app-main').innerHTML, /\/api\/tasks\/task-ready\/export/);
  app.navigate('review');
  assert.doesNotMatch(elements.get('app-main').innerHTML, /\/api\/tasks\/task-ready\/export/);
});

test('historical English review diagnostics are localized without changing audit codes', async () => {
  const detail = {
    id: 'task-legacy-basis', display_name: 'legacy.xls', template_version: 'A11', state: 'READY_FOR_REVIEW',
    updated_at: '2026-09-17T00:00:00Z', manual_decisions: [], revisions: [], source_files: [], stage_failures: [],
    rule_results: [{
      id: 'result-12', rule_id: 'TR-12', initial_status: 'NON_COMPLIANT', basis_code: 'ROLLUP_HARD_FAILURE',
      basis_text: 'A required material is missing or an objective check has failed. Atomic bases: FIELD_报告数据_MISSING, FIELD_小结_MISSING.',
      evidence_locators: [], missing_materials: [],
      unresolved_semantics: ['Data, summary, and conclusion consistency requires semantic review.']
    }]
  };
  const { app, elements } = bootRealPrototype(detail);

  await app.openRealTask(detail.id, 'review');
  const html = elements.get('app-main').innerHTML;

  assert.match(html, /缺少必需材料，或某项客观校验未通过。判定明细代码：FIELD_报告数据_MISSING、FIELD_小结_MISSING。/);
  assert.match(html, /数据、小结和结论的一致性需要语义审核。/);
  assert.match(html, /ROLLUP_HARD_FAILURE/);
  assert.doesNotMatch(html, /A required material|Atomic bases|requires semantic review/);
});

test('real mode polls only transient states and cancels on terminal navigation', () => {
  const source = read('app.js');
  for (const state of ['FILES_STAGED', 'PARSING', 'PARSED', 'EVALUATING']) assert.match(source, new RegExp(state));
  for (const state of ['READY_FOR_REVIEW', 'FAILED', 'COMPLETED']) assert.match(source, new RegExp(state));
  assert.match(source, /2000/);
  assert.match(source, /clearTimeout/);
  assert.doesNotMatch(source, /crypto\.randomUUID|Math\.random\(\).*task/i);
});
