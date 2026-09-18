(function () {
  const data = window.DEMO_DATA;
  const demoMode = !window.location || /(?:^|[?&])mode=demo(?:&|$)/.test(window.location.search || '');
  const api = demoMode ? null : new window.HardwareReviewApi.ApiClient();
  const formatLabel = data.supportedInputFormats.join(' · ');
  const sourceRowCount = data.rules.length;
  const executedRuleCount = data.rules.filter(rule => rule.enabled).length;
  const baselineLabel = `${sourceRowCount} 个源行 · ${executedRuleCount} 个执行项`;
  const state = {
    role: 'tester',
    view: 'dashboard',
    selectedTaskId: demoMode ? 'TASK-2026-092' : null,
    selectedRuleId: 'TR-12',
    createStep: 1,
    reportUploaded: false,
    selectedEvidence: ['JIRA记录', '原始记录'],
    createdTask: false,
    ruleEnabled: {},
    templateDraft: false,
    publishBlocked: false,
    filters: { status: '全部', query: '' },
    manualReviews: {},
    taskCompleted: false,
    reviewRevision: 1,
    completedRevisions: [],
    notices: [],
    realTasks: [],
    realTask: null,
    realLoading: !demoMode,
    realError: null,
    realTemplates: [],
    realTemplate: null,
    selectedTemplateId: null,
    createTemplateId: null,
    templateLoading: false,
    primaryReport: null,
    supportingFiles: []
  };

  const transientTaskStates = new Set(['FILES_STAGED', 'PARSING', 'PARSED', 'EVALUATING']);
  const terminalTaskStates = new Set(['READY_FOR_REVIEW', 'FAILED', 'COMPLETED']);
  const statusLabels = {
    COMPLIANT: '符合', NON_COMPLIANT: '不符合', NOT_APPLICABLE: '不适用', NEEDS_REVIEW: '待人工确认'
  };
  const legacyReviewTextTranslations = new Map([
    ['All checks in this source row are explicitly proven not applicable.', '本检查表来源行中的所有校验项均已有明确证据证明不适用。'],
    ['A required material is missing or an objective check has failed.', '缺少必需材料，或某项客观校验未通过。'],
    ['No hard failure was found, but a semantic obligation remains unresolved.', '未发现确定性不符合项，但仍有语义判断事项待确认。'],
    ['Every applicable deterministic obligation is positively evidenced.', '所有适用的客观校验项均已有明确证据证明符合。'],
    [' Atomic bases: ', '判定明细代码：'],
    ['JIRA link legality cannot be proven by literal rule matching.', '仅通过文字规则匹配无法证明 JIRA 链接有效性。'],
    ['Issue, status, and regression correspondence requires semantic review.', '问题、状态与回归记录的对应关系需要语义审核。'],
    ['Review closure and manager notification correspondence require semantic review.', '问题闭环与经理通知的对应关系需要语义审核。'],
    ['Adequacy of the limitation reason and outsourcing arrangement requires semantic review.', '能力限制原因及委外安排是否充分需要语义审核。'],
    ['Published report naming/version criteria were not supplied; no criterion is invented.', '未提供已发布的报告命名/版本标准；系统不会自行推断标准。'],
    ['Comparison with the supplied naming/version criterion requires semantic review.', '与已提供的命名/版本标准进行比对需要语义审核。'],
    ['The published homepage required-field list was not supplied; field names are not invented.', '未提供已发布的首页必填字段清单；系统不会自行推断字段名。'],
    ['Published criteria are present, but a traceable homepage required-field list cannot be read.', '已提供发布标准，但无法读取可追溯的首页必填字段清单。'],
    ['The homepage required-field list contains no traceable field names.', '首页必填字段清单中没有可追溯的字段名。'],
    ['Homepage-to-body consistency requires semantic review.', '首页与正文的一致性需要语义审核。'],
    ['The model/region/standard/use-case mapping was not supplied; no mapping is invented.', '未提供机型/区域/标准/使用场景映射；系统不会自行推断映射关系。'],
    ['Mandatory-case coverage against the supplied mapping requires semantic review.', '根据已提供映射核对应测用例覆盖情况需要语义审核。'],
    ['Completeness against the supplied required-item checklist requires semantic review.', '根据已提供的应测项清单核对完整性需要语义审核。'],
    ['Cross-record numeric equality requires semantic review.', '不同记录之间的数值一致性需要语义审核。'],
    ['Data, summary, and conclusion consistency requires semantic review.', '数据、小结和结论的一致性需要语义审核。'],
    ['No-omission and no-summary-loss judgment requires LLM or manual review.', '是否存在遗漏或小结信息丢失需要大语言模型或人工审核。'],
    ['EMC anomaly and JIRA correspondence requires semantic review.', 'EMC 异常与 JIRA 记录的对应关系需要语义审核。'],
    ['Unexplained conclusion conflicts across stages require semantic review.', '跨阶段存在的未解释结论冲突需要语义审核。'],
    ['Published ordering criteria were not supplied; no severity or ordering rule is invented.', '未提供已发布的排序标准；系统不会自行推断问题分级或排序规则。'],
    ['Emphasis and ordering against the supplied criteria require LLM or manual review.', '依据已提供标准核对强调内容和排序需要大语言模型或人工审核。'],
    ['Adequacy of the four fixed problem elements requires LLM or manual review.', '四个固定问题要素是否描述充分需要大语言模型或人工审核。'],
    ['Whether each conclusion expresses one independently actionable issue requires LLM or manual review.', '每条结论是否仅描述一个可独立处理的问题，需要大语言模型或人工审核。'],
    ['The published coating expectation was not supplied; no expected state is invented.', '未提供已发布的喷漆状态要求；系统不会自行推断预期状态。'],
    ['Comparison with the supplied coating expectation requires semantic review.', '与已提供的喷漆状态要求进行比对需要语义审核。']
  ]);
  const finalStatusValues = { '符合': 'COMPLIANT', '不符合': 'NON_COMPLIANT', '不适用': 'NOT_APPLICABLE' };
  const evidenceKindOptions = [
    ['JIRA_RECORD', 'JIRA记录'], ['PREVIOUS_STAGE_REPORT', '历史阶段报告'], ['POWER_RECORD', '功耗记录'],
    ['REQUIREMENT_OR_CASE_MAPPING', '需求/用例映射'], ['PAPER_RECORD', '纸质记录'], ['EMC_REPORT', 'EMC报告'],
    ['TEMPERATURE_RECORD', '温度记录'], ['AUTOMATION_RECORD', '自动化记录'], ['PUBLISHED_CRITERIA', '发布标准'], ['OTHER', '其他附件']
  ];
  let pollTimer = null;
  let pollGeneration = 0;

  const views = ['dashboard', 'tasks', 'create-task', 'review', 'templates', 'rule-editor'];
  const reviewViews = ['dashboard', 'tasks', 'create-task', 'review'];
  const templateViews = ['templates', 'rule-editor'];
  const main = document.getElementById('app-main');
  const nav = document.getElementById('primary-nav');

  const icons = {
    dashboard: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 13h6V4H4v9Zm0 7h6v-4H4v4Zm10 0h6v-9h-6v9Zm0-16v4h6V4h-6Z"/></svg>',
    tasks: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3h10a2 2 0 0 1 2 2v15l-7-3-7 3V5a2 2 0 0 1 2-2Zm1 5h8M8 12h6"/></svg>',
    create: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>',
    template: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h9l4 4v14H6V3Zm8 0v5h5M9 12h7M9 16h7"/></svg>',
    rule: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h10M18 7h2M4 17h2M10 17h10M14 4v6M8 14v6"/></svg>',
    arrow: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 18 6-6-6-6"/></svg>'
  };

  function escapeHtml(value) {
    return String(value).replace(/[&<>'"]/g, char => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    }[char]));
  }

  function localizeReviewText(value) {
    let text = String(value || '');
    for (const [source, translation] of legacyReviewTextTranslations) text = text.replaceAll(source, translation);
    const marker = '判定明细代码：';
    if (!text.includes(marker)) return text;
    const [summary, codes] = text.split(marker, 2);
    return `${summary}${marker}${codes.replace(/, /g, '、').replace(/\.$/, '。')}`;
  }

  function getState() {
    return JSON.parse(JSON.stringify(state));
  }

  function currentRole() {
    return data.roles.find(role => role.id === state.role) || null;
  }

  function hasReviewPermission() {
    return Boolean(currentRole()?.canReview);
  }

  function hasTemplatePermission() {
    return Boolean(currentRole()?.canManageTemplates);
  }

  function canNavigate(view) {
    if (!views.includes(view)) return false;
    if (reviewViews.includes(view)) return hasReviewPermission();
    if (templateViews.includes(view)) return hasTemplatePermission();
    return false;
  }

  function navigate(view) {
    if (!canNavigate(view)) return;
    if (!demoMode) stopPolling();
    if (!demoMode && view === 'tasks') {
      state.selectedTaskId = null;
      state.realTask = null;
    }
    state.view = view;
    if (view !== 'tasks') state.createdTask = false;
    render();
    main.focus({ preventScroll: true });
    if (!demoMode && (view === 'dashboard' || view === 'tasks')) refreshRealTasks();
    if (!demoMode && (view === 'templates' || view === 'create-task')) refreshRealTemplates();
  }

  function setRole(roleId) {
    if (!data.roles.some(role => role.id === roleId)) return;
    state.role = roleId;
    if (!canNavigate(state.view)) state.view = views.find(canNavigate);
    render();
  }

  function navButton(view, label, icon) {
    const active = state.view === view;
    return `<button class="nav-item${active ? ' is-active' : ''}" data-nav="${view}" aria-label="${escapeHtml(label)}" ${active ? 'aria-current="page"' : ''}>
      <span class="nav-icon">${icon}</span><span>${label}</span>
    </button>`;
  }

  function renderSidebar() {
    const review = hasReviewPermission() ? [
      navButton('dashboard', '审核工作台', icons.dashboard),
      navButton('tasks', '审核任务', icons.tasks),
      navButton('create-task', '创建任务', icons.create)
    ].join('') : '';
    const template = hasTemplatePermission() ? `
      <div class="nav-section-label">模板规则</div>
      ${navButton('templates', '模板管理', icons.template)}
      ${navButton('rule-editor', '模板规则编辑', icons.rule)}` : '';
    nav.innerHTML = `${review ? `<div class="nav-section-label">审核流程</div>${review}` : ''}${template}`;
  }

  function roleSwitcher() {
    return `<label class="role-switcher"><span>${demoMode ? '当前角色' : '权限演示（非身份认证）'}</span><select id="role-select" aria-label="切换当前角色">
      ${data.roles.map(role => `<option value="${role.id}" ${role.id === state.role ? 'selected' : ''}>${role.label}</option>`).join('')}
    </select></label>`;
  }

  function pageHeader(kicker, title, description, action = '') {
    return `<header class="page-header"><div><div class="eyebrow">${kicker}</div><h1>${title}</h1><p>${description}</p></div>
      <div class="header-actions">${roleSwitcher()}${action}</div></header>`;
  }

  function statusBadge(status) {
    const map = { '待人工复核': 'warning', '审核中': 'primary', '已结束': 'success' };
    const icon = status === '已结束' ? '✓' : status === '审核中' ? '◌' : '!';
    return `<span class="status-badge status-${map[status] || 'neutral'}"><b>${icon}</b>${status}</span>`;
  }

  function taskStateLabel(value) {
    return ({
      CREATED: '已创建', FILES_STAGED: '材料已暂存', PARSING: '正在解析', PARSED: '解析完成',
      EVALUATING: '正在审核', READY_FOR_REVIEW: '待人工复核', COMPLETED: '已结束', FAILED: '处理失败'
    })[value] || value;
  }

  function realTaskBadge(task) {
    if (task.state === 'COMPLETED') return statusBadge('已结束');
    if (task.state === 'READY_FOR_REVIEW') return statusBadge('待人工复核');
    if (task.state === 'FAILED') return '<span class="status-badge status-fail"><b>×</b>处理失败</span>';
    return statusBadge('审核中');
  }

  function realChecklistExportLink(task) {
    const taskId = encodeURIComponent(String(task.id || ''));
    return `<a class="btn btn-primary" href="/api/tasks/${taskId}/export" download>导出测试检查表</a>`;
  }

  function formatTime(value) {
    if (!value) return '—';
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? escapeHtml(value) : parsed.toLocaleString('zh-CN', { hour12: false });
  }

  function formatBytes(bytes) {
    if (!Number.isFinite(bytes)) return '—';
    if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  }

  function realErrorPanel() {
    if (!state.realError) return '';
    return `<div class="failure-card" role="alert"><span>!</span><div><strong>${escapeHtml(state.realError.code || 'REQUEST_FAILED')}</strong><p>${escapeHtml(state.realError.message || '请求失败')}</p></div></div>`;
  }

  function setRealError(error) {
    state.realError = { code: error.code || 'REQUEST_FAILED', message: error.message || String(error) };
  }

  function realResults(task = state.realTask) {
    if (!task) return [];
    const decisions = new Map((task.manual_decisions || []).map(item => [item.rule_result_id, item]));
    return (task.rule_results || []).map(result => {
      const definition = data.rules.find(item => item.ruleId === result.rule_id);
      const decision = decisions.get(result.id) || null;
      const initialStatus = statusLabels[result.initial_status] || result.initial_status;
      const finalStatus = decision ? statusLabels[decision.final_status] : (result.initial_status === 'NEEDS_REVIEW' ? null : initialStatus);
      return {
        result,
        definition,
        ruleId: result.rule_id,
        basisText: localizeReviewText(result.basis_text),
        unresolvedSemantics: (result.unresolved_semantics || []).map(localizeReviewText),
        initialStatus,
        finalStatus,
        displayStatus: finalStatus || initialStatus,
        manualReview: decision
      };
    });
  }

  function realReviewCounts() {
    const rows = realResults();
    return data.statuses.reduce((counts, label) => {
      counts[label] = rows.filter(item => item.displayStatus === label).length;
      return counts;
    }, {});
  }

  function realPendingCount() {
    return realResults().filter(item => item.result.initial_status === 'NEEDS_REVIEW' && !item.manualReview).length;
  }

  function stopPolling() {
    pollGeneration += 1;
    if (pollTimer !== null) window.clearTimeout(pollTimer);
    pollTimer = null;
  }

  function schedulePolling(taskId) {
    stopPolling();
    const generation = pollGeneration;
    const tick = async () => {
      if (generation !== pollGeneration || state.selectedTaskId !== taskId) return;
      try {
        const task = await api.getTask(taskId);
        if (generation !== pollGeneration) return;
        state.realTask = task;
        state.realError = null;
        render();
        if (transientTaskStates.has(task.state)) pollTimer = window.setTimeout(tick, 2000);
        else if (terminalTaskStates.has(task.state)) stopPolling();
      } catch (error) {
        setRealError(error);
        render();
        stopPolling();
      }
    };
    pollTimer = window.setTimeout(tick, 2000);
  }

  async function refreshRealTasks() {
    if (demoMode) return;
    state.realLoading = true;
    state.realError = null;
    render();
    try {
      const payload = await api.listTasks();
      state.realTasks = payload.tasks || [];
    } catch (error) {
      setRealError(error);
    } finally {
      state.realLoading = false;
      render();
    }
  }

  async function openRealTask(taskId, targetView = 'tasks') {
    stopPolling();
    state.selectedTaskId = taskId;
    state.view = targetView;
    state.realLoading = true;
    state.realError = null;
    render();
    try {
      state.realTask = await api.getTask(taskId);
      if (transientTaskStates.has(state.realTask.state)) schedulePolling(taskId);
    } catch (error) {
      setRealError(error);
    } finally {
      state.realLoading = false;
      render();
    }
  }

  async function refreshRealTemplates() {
    if (demoMode) return;
    state.templateLoading = true;
    state.realError = null;
    render();
    try {
      const payload = await api.listTemplates();
      state.realTemplates = payload.templates || [];
      const published = state.realTemplates.filter(item => item.status === 'PUBLISHED');
      if (!published.some(item => item.id === state.createTemplateId)) {
        state.createTemplateId = published[0]?.id || null;
      }
    } catch (error) {
      setRealError(error);
    } finally {
      state.templateLoading = false;
      render();
    }
  }

  async function openRealTemplate(templateId) {
    if (demoMode) return;
    state.selectedTemplateId = templateId;
    state.view = 'rule-editor';
    state.templateLoading = true;
    state.realError = null;
    render();
    try {
      state.realTemplate = await api.getTemplate(templateId);
      state.selectedRuleId = state.realTemplate.rules?.[0]?.rule_id || null;
    } catch (error) {
      setRealError(error);
    } finally {
      state.templateLoading = false;
      render();
    }
  }

  async function uploadRealTemplate() {
    const sourceInput = document.getElementById('template-source-input');
    const nameInput = document.getElementById('template-name-input');
    const versionInput = document.getElementById('template-version-input');
    const actorInput = document.getElementById('template-actor-input');
    const source = sourceInput?.files?.[0] || null;
    const name = String(nameInput?.value || '').trim();
    const version = String(versionInput?.value || '').trim();
    const actor = String(actorInput?.value || '').trim();
    if (!source || !name || !version || !actor) {
      setRealError({ code: 'TEMPLATE_METADATA_INVALID', message: '请选择 XLS，并填写模板名称、版本和操作人。' });
      render();
      return;
    }
    state.templateLoading = true;
    render();
    try {
      const created = await api.uploadTemplate({ source, name, version, actor });
      await refreshRealTemplates();
      await openRealTemplate(created.id);
      showToast('模板已上传为待发布版本');
    } catch (error) {
      setRealError(error);
      state.templateLoading = false;
      render();
    }
  }

  function selectedRealTemplateRule() {
    return state.realTemplate?.rules?.find(rule => rule.rule_id === state.selectedRuleId) || state.realTemplate?.rules?.[0] || null;
  }

  async function saveRealTemplateRule() {
    const rule = selectedRealTemplateRule();
    if (!rule || state.realTemplate?.template?.status !== 'DRAFT') return;
    const summary = document.getElementById('template-rule-summary');
    const requirement = document.getElementById('template-rule-requirement');
    const materials = document.getElementById('template-rule-materials');
    const judgment = document.getElementById('template-rule-judgment');
    const boundary = document.getElementById('template-rule-boundary');
    try {
      await api.updateTemplateRule(state.selectedTemplateId, rule.rule_id, {
        summary: summary?.value || '',
        verifiable_requirement: requirement?.value || '',
        required_materials: materials?.value || '',
        main_judgment: judgment?.value || rule.main_judgment,
        confirmed_boundary: boundary?.value || ''
      });
      await openRealTemplate(state.selectedTemplateId);
      showToast('规则修改已保存');
    } catch (error) {
      setRealError(error);
      render();
    }
  }

  async function toggleRealTemplateRule(ruleId) {
    const rule = state.realTemplate?.rules?.find(item => item.rule_id === ruleId);
    if (!rule || state.realTemplate?.template?.status !== 'DRAFT') return;
    try {
      await api.updateTemplateRule(state.selectedTemplateId, ruleId, {
        enabled: !rule.enabled,
        main_judgment: rule.enabled ? 'DISABLED' : 'MANUAL'
      });
      await openRealTemplate(state.selectedTemplateId);
    } catch (error) {
      setRealError(error);
      render();
    }
  }

  async function addRealTemplateRule() {
    if (state.realTemplate?.template?.status !== 'DRAFT') return;
    const used = new Set((state.realTemplate.rules || []).map(rule => rule.rule_id));
    let index = 1;
    while (used.has(`CUSTOM-${String(index).padStart(2, '0')}`)) index += 1;
    try {
      const added = await api.addTemplateRule(state.selectedTemplateId, {
        rule_id: `CUSTOM-${String(index).padStart(2, '0')}`,
        summary: '新增人工检查项',
        verifiable_requirement: '请填写可验证的检查要求',
        required_materials: '请填写所需证明材料',
        main_judgment: 'MANUAL',
        confirmed_boundary: '未配置自动判定条件时进入待人工确认',
        enabled: true
      });
      await openRealTemplate(state.selectedTemplateId);
      state.selectedRuleId = added.rule_id;
      render();
      showToast('已新增人工检查项，请完善规则内容');
    } catch (error) {
      setRealError(error);
      render();
    }
  }

  async function deleteRealTemplateRule(ruleId) {
    if (state.realTemplate?.template?.status !== 'DRAFT') return;
    try {
      await api.deleteTemplateRule(state.selectedTemplateId, ruleId);
      await openRealTemplate(state.selectedTemplateId);
      showToast('规则已从当前草稿删除');
    } catch (error) {
      setRealError(error);
      render();
    }
  }

  async function publishRealTemplate() {
    try {
      await api.publishTemplate(state.selectedTemplateId);
      await openRealTemplate(state.selectedTemplateId);
      showToast('模板版本已发布');
    } catch (error) {
      setRealError(error);
      render();
    }
  }

  async function retireRealTemplate() {
    try {
      await api.retireTemplate(state.selectedTemplateId);
      await openRealTemplate(state.selectedTemplateId);
      showToast('模板版本已停用，历史记录保持不变');
    } catch (error) {
      setRealError(error);
      render();
    }
  }

  async function executeRealTask(taskId) {
    state.realLoading = true;
    state.realError = null;
    render();
    try {
      const claimed = await api.executeTask(taskId);
      state.realTask = { ...(state.realTask || {}), ...claimed };
      if (transientTaskStates.has(claimed.state)) schedulePolling(taskId);
      else state.realTask = await api.getTask(taskId);
    } catch (error) {
      setRealError(error);
    } finally {
      state.realLoading = false;
      render();
    }
  }

  async function createRealTask() {
    if (!state.createTemplateId || !state.primaryReport || state.supportingFiles.some(item => !item.evidenceKinds.length)) {
      state.realError = { code: 'INVALID_UPLOAD', message: '请选择已发布模板和主报告，并为每个支撑文件至少选择一种证据类型。' };
      render();
      return;
    }
    state.realLoading = true;
    state.realError = null;
    render();
    try {
      const created = await api.createTask({ templateId: state.createTemplateId, primaryReport: state.primaryReport, supportingFiles: state.supportingFiles });
      state.selectedTaskId = created.id;
      state.realTask = created;
      state.view = 'tasks';
      await executeRealTask(created.id);
    } catch (error) {
      setRealError(error);
      state.realLoading = false;
      render();
    }
  }

  async function saveRealDecision() {
    const status = document.getElementById('manual-final-status');
    const reason = document.getElementById('manual-review-reason');
    if (!status || !reason || !status.value || !reason.value.trim()) {
      showToast('请选择最终状态并填写修改原因');
      return;
    }
    try {
      await api.saveManualDecision(state.selectedTaskId, state.selectedRuleId, {
        finalStatus: status.value,
        reason: reason.value.trim(),
        supplementalEvidence: []
      });
      state.realTask = await api.getTask(state.selectedTaskId);
      state.realError = null;
      render();
      showToast('人工判定已保存');
    } catch (error) {
      setRealError(error);
      render();
    }
  }

  async function completeRealTask() {
    try {
      await api.completeTask(state.selectedTaskId);
      state.realTask = await api.getTask(state.selectedTaskId);
      state.realError = null;
      render();
      showToast('审核已完成，修订快照已保存');
    } catch (error) {
      setRealError(error);
      render();
    }
  }

  async function reopenRealTask() {
    try {
      await api.reopenTask(state.selectedTaskId);
      state.realTask = await api.getTask(state.selectedTaskId);
      state.realError = null;
      render();
      showToast(`已重新打开，第 ${state.realTask.active_revision_no + 1} 次审核可继续处理`);
    } catch (error) {
      setRealError(error);
      render();
    }
  }

  function renderModeBanner() {
    return `<div class="mode-banner ${demoMode ? 'is-demo' : 'is-real'}"><b>${demoMode ? '演示模式' : '真实 API 模式'}</b><span>${demoMode ? '页面使用固定示例数据；移除 ?mode=demo 可返回真实 API 模式。' : '任务、状态、数量和审核结果均来自本机服务。角色切换仅用于权限演示，不代表身份认证。'}</span></div>`;
  }

  function renderRealDashboard() {
    const ready = state.realTasks.filter(item => item.state === 'READY_FOR_REVIEW').length;
    const running = state.realTasks.filter(item => transientTaskStates.has(item.state) || item.state === 'CREATED').length;
    const completed = state.realTasks.filter(item => item.state === 'COMPLETED').length;
    const rows = state.realTasks.slice(0, 6).map(task => `<button class="task-row" data-action="open-real-task" data-task="${task.id}">
      <span class="file-mark">${escapeHtml(task.display_name.slice(0, 1))}</span><span class="task-main"><strong>${escapeHtml(task.display_name)}</strong><small>任务 ${task.id} · 模板 ${escapeHtml(task.template_version)}</small></span>
      <span class="task-progress"><b>${(task.rule_results || []).length} / ${task.template_rule_count || 21}</b><small>已生成结果</small></span>${realTaskBadge(task)}<span class="task-time">${formatTime(task.updated_at)}</span><span class="row-arrow">${icons.arrow}</span>
    </button>`).join('') || '<div class="empty-state">尚无审核任务</div>';
    return `${pageHeader('TEST REVIEW WORKSPACE', '审核工作台', '任务数据来自本机审核服务。', '<button class="btn btn-primary" data-nav="create-task">＋ 创建审核任务</button>')}
      ${renderModeBanner()}${realErrorPanel()}<section class="metric-grid" aria-label="任务概览">
      <article class="metric-card metric-attention"><div class="metric-icon">待</div><div><span>待人工复核</span><strong>${ready}</strong><small>需人工形成最终状态</small></div></article>
      <article class="metric-card"><div class="metric-icon blue">审</div><div><span>处理中</span><strong>${running}</strong><small>解析或规则审核进行中</small></div></article>
      <article class="metric-card"><div class="metric-icon green">完</div><div><span>已结束</span><strong>${completed}</strong><small>已生成不可变修订快照</small></div></article></section>
      <section class="panel recent-panel"><div class="panel-heading"><div><h2>最近任务</h2><p>按服务返回顺序展示</p></div><button class="text-button" data-nav="tasks">查看全部 ${icons.arrow}</button></div><div class="task-list">${state.realLoading ? '<div class="empty-state">正在读取任务…</div>' : rows}</div></section>`;
  }

  function renderRealTasks() {
    if (state.selectedTaskId && state.realTask) return renderRealTaskDetail();
    const rows = state.realTasks.map(task => `<tr><td><strong>${escapeHtml(task.display_name)}</strong><small>${task.id}</small></td><td>${escapeHtml(task.template_version)}</td><td>本机服务</td><td>${(task.rule_results || []).length} / ${task.template_rule_count || 21}</td><td>${realTaskBadge(task)}</td><td>${formatTime(task.updated_at)}</td><td><button class="table-action" data-action="open-real-task" data-task="${task.id}">查看</button></td></tr>`).join('');
    return `${pageHeader('REVIEW TASKS', '审核任务', '查看持久化任务、来源材料和当前处理状态。', '<button class="btn btn-primary" data-nav="create-task">＋ 创建审核任务</button>')}
      ${renderModeBanner()}${realErrorPanel()}<section class="panel"><div class="table-wrap"><table><thead><tr><th>报告</th><th>模板</th><th>来源</th><th>结果数</th><th>状态</th><th>更新时间</th><th></th></tr></thead><tbody>${rows || '<tr><td colspan="7">尚无审核任务</td></tr>'}</tbody></table></div></section>`;
  }

  function renderRealCreateTask() {
    const publishedTemplates = state.realTemplates.filter(item => item.status === 'PUBLISHED');
    const selectedTemplate = publishedTemplates.find(item => item.id === state.createTemplateId) || null;
    const templateChoices = publishedTemplates.map(template => `<button class="template-choice${template.id === state.createTemplateId ? ' is-selected' : ''}" data-action="select-real-template" data-template="${escapeHtml(template.id)}" aria-pressed="${template.id === state.createTemplateId}"><span class="sheet-icon">XLS</span><span><strong>${escapeHtml(template.name)}</strong><small>版本 ${escapeHtml(template.version)} · ${template.source_rows} 个源行 · ${template.effective_rules} 个执行项</small></span><span class="choice-check">${template.id === state.createTemplateId ? '✓' : ''}</span></button>`).join('');
    const supportRows = state.supportingFiles.map((item, index) => `<article class="support-file-card"><div><strong>${escapeHtml(item.file.name)}</strong><small>${formatBytes(item.file.size)} · 支撑证据</small></div><fieldset><legend>证据类型（至少一项）</legend>${evidenceKindOptions.map(([value, label]) => `<label><input type="checkbox" data-support-kind="${value}" data-index="${index}" ${item.evidenceKinds.includes(value) ? 'checked' : ''}>${label}</label>`).join('')}</fieldset></article>`).join('');
    const valid = selectedTemplate && state.primaryReport && state.supportingFiles.every(item => item.evidenceKinds.length);
    return `${pageHeader('CREATE REVIEW TASK', '创建审核任务', '上传一份主报告，并为每份支撑材料标注证据类型。')}
      ${renderModeBanner()}${realErrorPanel()}<section class="panel wizard-panel"><div class="wizard-body">
      <div class="form-heading"><span>01</span><div><h2>选择已发布审核模板</h2><p>任务创建后冻结所选版本；管理员后续停用模板不影响本任务。</p></div></div>
      <div class="template-choice-list">${templateChoices || '<div class="empty-state">当前没有可用的已发布模板</div>'}</div>
      <label class="file-picker"><span>主测试报告 <b>必填</b></span><input id="primary-report-input" type="file" accept=".pdf,.doc,.docx,.xls,.xlsx"><small>${state.primaryReport ? `${escapeHtml(state.primaryReport.name)} · ${formatBytes(state.primaryReport.size)} · 主报告` : `支持 ${formatLabel}`}</small></label>
      <label class="file-picker"><span>支撑证据 <b>选填</b></span><input id="supporting-files-input" type="file" multiple accept=".pdf,.doc,.docx,.xls,.xlsx"><small>每个支撑文件必须选择至少一种证据类型</small></label>
      <div class="warning-strip" role="note"><span>!</span><p><strong>旧版 Word 格式提醒</strong>DOC/DOCX 依赖本机 Microsoft Word；WPS 不作为兼容依据。如同时有同内容 PDF，请优先上传 PDF，避免重复上传对应 DOC。</p></div>
      <div class="supporting-list">${supportRows}</div>
      <div class="safety-strip"><span>锁</span><p><strong>源文件保护</strong>服务仅处理生成的任务副本，不修改原报告。</p></div></div>
      <footer class="wizard-footer"><button class="btn btn-secondary" data-nav="dashboard">取消</button><button class="btn btn-primary" data-action="create-real-task" ${valid && !state.realLoading ? '' : 'disabled'}>${state.realLoading ? '正在创建…' : '创建并开始审核'}</button></footer></section>`;
  }

  function renderRealTaskDetail() {
    const task = state.realTask;
    if (!task) return `${pageHeader('REVIEW TASK', '审核任务', '正在读取任务。')}${realErrorPanel()}`;
    const results = realResults(task);
    const failures = task.stage_failures || [];
    const action = task.state === 'READY_FOR_REVIEW' ? '<button class="btn btn-primary" data-action="open-real-review">进入人工复核</button>'
      : task.state === 'COMPLETED' ? `${realChecklistExportLink(task)}<button class="btn btn-secondary" data-action="open-real-review">查看审核结果</button>`
        : task.state === 'FAILED' ? '<button class="btn btn-secondary" data-nav="create-task">重新上传材料</button>' : '';
    const failureHtml = failures.map(item => `<div class="failure-card"><span>!</span><div><strong>材料解析失败 · ${escapeHtml(item.stage)}</strong><p>${escapeHtml(displayedFailureMessage(task, item))}</p><small>${escapeHtml(item.code)}</small></div></div>`).join('');
    const stages = ['FILES_STAGED', 'PARSING', 'PARSED', 'EVALUATING', 'READY_FOR_REVIEW'].map(value => `<div class="stage-node ${task.state === value ? 'is-current' : ''}"><b>${taskStateLabel(value)}</b></div>`).join('');
    return `${pageHeader('REVIEW TASK', escapeHtml(task.display_name), `任务 ${task.id} · 模板 ${escapeHtml(task.template_version)}`, action)}
      ${renderModeBanner()}${realErrorPanel()}${failureHtml}<section class="panel detail-hero"><div>${realTaskBadge(task)}<h2>${taskStateLabel(task.state)}</h2><p>系统已生成 ${results.length} / ${task.template_rule_count || 21} 个有效校验结果。</p></div><div class="detail-score"><span>${results.length} / ${task.template_rule_count || 21}</span><small>规则结果</small></div></section>
      <section class="panel timeline-panel"><div class="panel-heading"><div><h2>审核进度</h2><p>状态与错误均来自 API</p></div></div><div class="stage-grid">${stages}</div></section>
      <section class="panel"><div class="panel-heading"><div><h2>来源材料</h2><p>持久化清单，不显示服务内部路径</p></div></div><div class="supporting-list">${(task.source_files || []).map(item => `<div class="uploaded-file"><span class="doc-icon">${item.detected_format}</span><div><strong>${escapeHtml(item.original_name)}</strong><small>${item.role === 'PRIMARY_REPORT' ? '主报告' : `支撑证据 · ${(item.evidence_kinds || []).join('、')}`}</small></div><span>${formatBytes(item.size_bytes)}</span></div>`).join('')}</div></section>`;
  }

  function displayedFailureMessage(task, failure) {
    const message = String(failure.message || '');
    const sources = task.source_files || [];
    if (sources.some(source => message.includes(source.original_name))) return message;
    if (failure.code !== 'DOC_CONVERSION_FAILED') return message;
    const candidates = sources.filter(source => ['DOC', 'DOCX'].includes(source.detected_format));
    if (candidates.length === 1) return `${candidates[0].original_name}: ${message}`;
    if (candidates.length > 1) return `DOC/DOCX 材料（${candidates.map(item => item.original_name).join('、')}）: ${message}`;
    return message;
  }

  function locatorText(locator) {
    const source = (state.realTask?.source_files || []).find(item => item.id === locator.source_file_id);
    const format = source?.detected_format || 'FILE';
    const address = [locator.container, locator.structural_address].filter(Boolean).join(' · ');
    const region = locator.bbox ? ` · 区域 ${locator.bbox.join(', ')}` : '';
    return `${format} · ${source?.original_name || locator.source_file_id} · ${address}${region}`;
  }

  function renderRealReview() {
    const task = state.realTask;
    if (!task) return `${pageHeader('EVIDENCE REVIEW', '审核结果', '请选择任务。')}${realErrorPanel()}`;
    const allRows = realResults(task);
    const counts = realReviewCounts();
    const pending = realPendingCount();
    const query = state.filters.query.trim().toLowerCase();
    const rows = allRows.filter(item => (state.filters.status === '全部' || item.displayStatus === state.filters.status) && (!query || `${item.ruleId} ${item.definition?.title || ''} ${item.basisText}`.toLowerCase().includes(query)));
    const selected = allRows.find(item => item.ruleId === state.selectedRuleId) || rows[0] || allRows[0];
    if (selected) state.selectedRuleId = selected.ruleId;
    const filters = ['全部', ...data.statuses].map(label => `<button class="filter-chip${state.filters.status === label ? ' is-active' : ''}" data-review-filter="${label}">${label} ${label === '全部' ? allRows.length : counts[label] || 0}</button>`).join('');
    const list = rows.map(item => `<button class="rule-row${item.ruleId === selected?.ruleId ? ' is-selected' : ''}" data-rule="${item.ruleId}"><span class="rule-seq">${item.definition ? String(item.definition.seq).padStart(2, '0') : '—'}</span><span><b>${escapeHtml(item.definition?.title || item.ruleId)}</b><small>${item.ruleId} · ${escapeHtml(item.result.basis_code)}</small></span>${resultStatusBadge(item.displayStatus)}</button>`).join('') || '<div class="empty-state">没有匹配的校验项</div>';
    const evidence = selected ? selected.result.evidence_locators || [] : [];
    const evidenceHtml = evidence.length ? evidence.map(locator => `<div class="evidence-link"><span>⌖</span><p><b>${escapeHtml(locatorText(locator))}</b>${locator.quoted_text ? `<small>${escapeHtml(locator.quoted_text)}</small>` : ''}</p></div>`).join('') : `<div class="empty-state">${escapeHtml([...(selected?.result.missing_materials || []), ...(selected?.unresolvedSemantics || [])].join('；') || '未提供可定位证据')}</div>`;
    const decision = selected?.manualReview;
    const action = task.state === 'COMPLETED' ? `${realChecklistExportLink(task)}<button class="btn btn-secondary" data-action="reopen-real-task">重新打开审核</button>` : `<button class="btn btn-primary" data-action="complete-real-task" ${pending ? `disabled title="仍有 ${pending} 项待人工确认"` : ''}>完成审核</button>`;
    const manualForm = task.state === 'READY_FOR_REVIEW' && selected ? `<form class="manual-decision-form"><div class="manual-review-heading"><span>!</span><div><h3>人工最终判定</h3><p>人工结论优先；修改原因必填，补充证据不强制。</p></div></div><label><span>最终状态 <b>必填</b></span><select id="manual-final-status" required><option value="" disabled ${decision ? '' : 'selected'}>请选择最终状态</option>${Object.entries(finalStatusValues).map(([label, value]) => `<option value="${value}" ${decision?.final_status === value ? 'selected' : ''}>${label}</option>`).join('')}</select></label><label><span>修改原因 <b>必填</b></span><textarea id="manual-review-reason" rows="3" required>${escapeHtml(decision?.reason || '')}</textarea></label><button type="button" class="btn btn-primary" data-action="save-real-decision">保存人工判定</button></form>` : '';
    return `<div class="review-page">${pageHeader(`EVIDENCE REVIEW · ${escapeHtml(task.template_version)}`, '审核结果', `${escapeHtml(task.display_name)} · ${task.id}`, action)}${renderModeBanner()}${realErrorPanel()}
      <section class="review-summary"><div><span>有效校验项</span><strong>${allRows.length} / ${task.template_rule_count || allRows.length}</strong></div><i></i><div><span>符合</span><strong class="green-text">${counts['符合'] || 0}</strong></div><div><span>不符合</span><strong class="red-text">${counts['不符合'] || 0}</strong></div><div><span>不适用</span><strong>${counts['不适用'] || 0}</strong></div><div><span>待人工确认</span><strong class="amber-text">${pending}</strong></div><p><span>●</span> ${task.state === 'COMPLETED' ? `已完成 ${task.revisions?.length || 0} 个修订快照` : pending ? `仍有 ${pending} 项必须人工复核` : '全部项目已有最终状态，可完成审核'}</p></section>
      <section class="review-toolbar"><div class="filter-row">${filters}</div><label class="search-box"><span>⌕</span><input id="review-search" value="${escapeHtml(state.filters.query)}" placeholder="搜索规则或依据"></label></section>
      <section class="review-workbench"><aside class="rule-list-panel"><div class="column-title"><div><b>${escapeHtml(task.template_version)} 执行结果</b><small>${task.template_rule_count || allRows.length} 个冻结启用项</small></div></div><div class="rule-list">${list}</div></aside>
      <article class="evidence-panel"><div class="column-title"><div><b>可追溯证据</b><small>${selected ? selected.ruleId : '—'}</small></div><span class="read-only">只读</span></div><div class="decision-body">${evidenceHtml}</div></article>
      <aside class="decision-panel"><div class="column-title"><div><b>问题详情</b><small>${selected ? selected.ruleId : '—'}</small></div>${selected ? resultStatusBadge(selected.displayStatus) : ''}</div><div class="decision-body">${selected ? `<section class="decision-status-grid"><div><h3>系统初判</h3>${resultStatusBadge(selected.initialStatus)}</div><div><h3>人工最终状态</h3>${selected.finalStatus ? resultStatusBadge(selected.finalStatus) : '<span class="result-status result-pending"><b>?</b>待人工处理</span>'}</div></section>${decision ? `<section class="manual-decision-record"><h3>人工复核记录</h3><p>${escapeHtml(decision.reason)}</p><small>${escapeHtml(decision.actor)} · ${formatTime(decision.decided_at)}</small></section>` : ''}<section><h3>系统判定依据</h3><p>${escapeHtml(selected.basisText)}</p></section>${manualForm}` : '<div class="empty-state">暂无结果</div>'}</div></aside></section></div>`;
  }

  function renderDashboard() {
    const counts = reviewCounts();
    if (!demoMode) return renderRealDashboard();
    const action = '<button class="btn btn-primary" data-nav="create-task"><span>＋</span>创建审核任务</button>';
    const rows = data.tasks.map(task => `<button class="task-row" data-task="${task.id}" data-nav="${task.status === '待人工复核' ? 'review' : 'tasks'}">
      <span class="file-mark">${task.name.slice(0, 1)}</span><span class="task-main"><strong>${escapeHtml(task.name)}</strong><small>任务 ${task.id} · 模板 ${task.template} · ${task.owner}</small></span>
      <span class="task-progress"><b>${task.progress}</b><small>校验进度</small></span>${statusBadge(task.status)}<span class="task-time">${task.updated}</span><span class="row-arrow">${icons.arrow}</span>
    </button>`).join('');
    return `${pageHeader('TEST REVIEW WORKSPACE', '审核工作台', '集中查看待处理任务、审核进度与本月交付情况。', action)}
      <section class="metric-grid" aria-label="任务概览">
        <article class="metric-card metric-attention"><div class="metric-icon">待</div><div><span>待人工复核</span><strong>3</strong><small>当前任务有 ${counts['待人工确认']} 项等待结论</small></div><em>需处理</em></article>
        <article class="metric-card"><div class="metric-icon blue">审</div><div><span>审核处理中</span><strong>2</strong><small>平均已完成 64%</small></div><em class="neutral">进行中</em></article>
        <article class="metric-card"><div class="metric-icon green">完</div><div><span>本月已结束</span><strong>46</strong><small>已生成 46 份审核副本</small></div><em class="success">+12%</em></article>
      </section>
      <section class="dashboard-grid"><article class="panel recent-panel"><div class="panel-heading"><div><h2>最近任务</h2><p>按最近更新时间排序</p></div><button class="text-button" data-nav="tasks">查看全部 ${icons.arrow}</button></div><div class="task-list">${rows}</div></article>
        <aside class="panel insight-panel"><div class="panel-heading"><div><h2>审核概览</h2><p>近 30 天</p></div></div><div class="ring-wrap"><div class="ring"><span><strong>92%</strong><small>已复核</small></span></div></div>
          <div class="insight-legend"><div><span class="dot green"></span><b>${counts['符合']}</b><small>符合</small></div><div><span class="dot red"></span><b>${counts['不符合']}</b><small>不符合</small></div><div><span class="dot muted"></span><b>${counts['不适用']}</b><small>不适用</small></div><div><span class="dot amber"></span><b>${counts['待人工确认']}</b><small>待人工确认</small></div></div>
          <div class="notice-card"><span>i</span><p><strong>审核原则</strong>智能体只提供问题与证据，不代替人工作出报告通过结论。</p></div></aside></section>`;
  }

  function renderTasks() {
    if (!demoMode) return renderRealTasks();
    if (state.createdTask) return renderTaskDetail();
    const rows = data.tasks.map(task => `<tr><td><strong>${escapeHtml(task.name)}</strong><small>${task.id}</small></td><td>${task.template}</td><td>${task.owner}</td><td>${task.progress}</td><td>${statusBadge(task.status)}</td><td>${task.updated}</td><td><button class="table-action" data-task="${task.id}" data-nav="${task.status === '待人工复核' ? 'review' : 'tasks'}">查看</button></td></tr>`).join('');
    return `${pageHeader('REVIEW TASKS', '审核任务', '查看所有审核任务及当前处理状态。', '<button class="btn btn-primary" data-nav="create-task">＋ 创建审核任务</button>')}
      <section class="panel"><div class="toolbar"><div class="segmented"><button class="is-active">全部</button><button>待人工复核</button><button>审核中</button><button>已结束</button></div><label class="search-box"><span>⌕</span><input placeholder="搜索报告或任务编号"></label></div>
      <div class="table-wrap"><table><thead><tr><th>报告</th><th>模板</th><th>创建人</th><th>校验进度</th><th>状态</th><th>更新时间</th><th></th></tr></thead><tbody>${rows}</tbody></table></div></section>`;
  }

  function wizardStep(number, label) {
    const current = state.createStep === number;
    const complete = state.createStep > number;
    return `<div class="wizard-step${current ? ' is-current' : ''}${complete ? ' is-complete' : ''}"><span>${complete ? '✓' : number}</span><b>${label}</b></div>`;
  }

  function renderCreateTask() {
    if (!demoMode) return renderRealCreateTask();
    const steps = [
      wizardStep(1, '选择审核模板'),
      wizardStep(2, '上传测试报告'),
      wizardStep(3, '上传支撑证据'),
      wizardStep(4, '确认并创建')
    ].join('<i></i>');
    const evidenceTypes = ['JIRA记录', '历史报告', '原始记录', '截图', '其他附件'];
    let body = '';
    if (state.createStep === 1) {
      body = `<div class="form-heading"><span>01</span><div><h2>选择审核模板</h2><p>仅可选择处于“已发布”状态的模板。</p></div></div>
        <button class="template-choice is-selected" aria-pressed="true"><span class="sheet-icon">XLS</span><span><strong>硬件测试过程检查单</strong><small>正式版本 A11 · ${baselineLabel}</small></span><span class="choice-check">✓</span></button>
        <div class="context-note"><b>版本固定</b><p>任务创建后始终关联当前 A11 版本；管理员后续发布新版本不会改变本任务。</p></div>`;
    } else if (state.createStep === 2) {
      body = `<div class="form-heading"><span>02</span><div><h2>上传测试报告</h2><p>主报告为必填，支持 ${formatLabel}。</p></div></div>
        ${state.reportUploaded ? `<div class="uploaded-file"><span class="doc-icon">DOCX</span><div><strong>X92_PP阶段硬件测试报告_A03.docx</strong><small>12.8 MB · 已完成读取检查</small></div><span class="upload-ok">✓ 可用</span><button class="icon-button" data-action="remove-report" aria-label="移除报告">×</button></div>` : `<button class="upload-zone" data-action="demo-upload"><span class="upload-symbol">⇧</span><strong>拖放主报告到此处，或点击选择文件</strong><small>原型演示：点击后载入示例 DOCX，不会读取本地文件</small><em>${formatLabel}</em></button>`}
        <div class="safety-strip"><span>锁</span><p><strong>源文件保护</strong>审核过程只读取上传副本，不会修改或覆盖原测试报告。</p></div>`;
    } else if (state.createStep === 3) {
      body = `<div class="form-heading"><span>03</span><div><h2>上传支撑证据</h2><p>外部材料缺失不会阻止创建，但缺少必需证据的校验项将判为“不符合”。</p></div></div>
        <div class="evidence-grid">${evidenceTypes.map((type, index) => {
          const selected = state.selectedEvidence.includes(type);
          return `<button class="evidence-card${selected ? ' is-added' : ''}" data-action="toggle-evidence" data-evidence="${type}" aria-pressed="${selected}"><span>${selected ? '✓' : '+'}</span><strong>${type}</strong><small>${index === 0 ? '项目页面截图或导出记录' : index === 1 ? '以前阶段测试报告' : index === 2 ? '测试原始表或扫描件' : index === 3 ? '关键页面或设备照片' : '其他可追溯材料'}</small></button>`;
        }).join('')}</div>
        <div class="warning-strip"><span>!</span><p><strong>仍缺少 3 类必需证据</strong>历史报告、关键截图与其他附件未添加，TR-02、TR-13、TR-22 将判为“不符合”。</p></div>`;
    } else {
      body = `<div class="form-heading"><span>04</span><div><h2>确认并创建</h2><p>核对报告、模板和支撑证据后开始审核。</p></div></div>
        <div class="summary-grid"><div><small>审核模板</small><strong>硬件测试过程检查单 A11</strong><span>${baselineLabel}</span></div><div><small>主测试报告</small><strong>X92_PP阶段硬件测试报告_A03.docx</strong><span>12.8 MB</span></div><div><small>已添加证据</small><strong>${state.selectedEvidence.length} 类材料</strong><span>${state.selectedEvidence.join('、') || '未添加'}</span></div></div>
        <div class="warning-strip"><span>!</span><p><strong>缺少必需证据将判为“不符合”</strong>请在创建任务前核对材料清单，系统会在结果页列出缺失证据及对应校验要求。</p></div>`;
    }
    const canContinue = state.createStep !== 2 || state.reportUploaded;
    return `${pageHeader('CREATE REVIEW TASK', '创建审核任务', '选择 A11 模板并准备测试报告与可追溯证据。')}
      <section class="wizard-bar">${steps}</section><section class="panel wizard-panel"><div class="wizard-body">${body}</div>
      <footer class="wizard-footer"><button class="btn btn-secondary" ${state.createStep === 1 ? 'data-nav="dashboard"' : 'data-action="wizard-back"'}>${state.createStep === 1 ? '取消' : '上一步'}</button>
      <div><span class="step-count">步骤 ${state.createStep} / 4</span><button class="btn btn-primary" data-action="${state.createStep === 4 ? 'create-demo-task' : 'wizard-next'}" ${canContinue ? '' : 'disabled'}>${state.createStep === 4 ? '开始审核' : '继续'}</button></div></footer></section>`;
  }

  function advanceCreateStep() {
    if (state.createStep === 2 && !state.reportUploaded) return;
    state.createStep = Math.min(4, state.createStep + 1);
    render();
  }

  function createDemoTask() {
    state.selectedTaskId = 'TASK-2026-093';
    state.createdTask = true;
    state.view = 'tasks';
    render();
  }

  function renderTaskDetail() {
    const counts = reviewCounts();
    const pending = counts['待人工确认'];
    const timeline = [
      ['上传完成', '今天 17:02', 'done'], ['规则审核', `${executedRuleCount} 项完成`, 'done'], ['AI 审核', '7 项完成', 'done'], ['等待人工复核', '当前阶段', 'current'], ['任务结束', '待处理', 'pending']
    ].map(([label, meta, status]) => `<div class="timeline-node ${status}"><span>${status === 'done' ? '✓' : status === 'current' ? '4' : '5'}</span><b>${label}</b><small>${meta}</small></div>`).join('<i></i>');
    return `${pageHeader('REVIEW TASK', 'X92 PP阶段硬件测试报告', `任务 ${escapeHtml(state.selectedTaskId)} · 模板 A11 · 创建人 陈工`, '<button class="btn btn-primary" data-nav="review">进入人工复核</button>')}
      <section class="panel detail-hero"><div><span class="status-badge status-warning"><b>!</b>待人工复核</span><h2>自动审核已完成</h2><p>${baselineLabel}，其中 ${pending} 项需要人工确认后才能完成审核。</p></div><div class="detail-score"><span>${executedRuleCount - pending} / ${executedRuleCount}</span><small>已形成最终状态</small></div></section>
      <section class="panel timeline-panel"><div class="panel-heading"><div><h2>审核进度</h2><p>从材料上传到任务结束的完整过程</p></div></div><div class="review-timeline">${timeline}</div></section>
      <section class="result-cards"><article><span class="result-icon ok">✓</span><div><strong>${counts['符合']}</strong><small>符合</small></div></article><article><span class="result-icon bad">×</span><div><strong>${counts['不符合']}</strong><small>不符合</small></div></article><article><span class="result-icon muted">—</span><div><strong>${counts['不适用']}</strong><small>不适用</small></div></article><article><span class="result-icon pending">?</span><div><strong>${counts['待人工确认']}</strong><small>待人工确认</small></div></article></section>`;
  }

  function resultStatusBadge(status) {
    const styles = { '符合': 'pass', '不符合': 'fail', '不适用': 'na', '待人工确认': 'pending' };
    const iconsByStatus = { '符合': '✓', '不符合': '×', '不适用': '—', '待人工确认': '?' };
    return `<span class="result-status result-${styles[status]}"><b>${iconsByStatus[status]}</b>${status}</span>`;
  }

  function effectiveRule(rule) {
    const manualReview = state.manualReviews[rule.ruleId] ? { ...state.manualReviews[rule.ruleId] } : null;
    const implicitFinal = rule.initialStatus === '待人工确认' ? null : rule.initialStatus;
    const finalStatus = manualReview ? manualReview.status : implicitFinal;
    return { ...rule, finalStatus, displayStatus: finalStatus || rule.initialStatus, manualReview };
  }

  function reviewRules() {
    return data.rules.filter(rule => rule.enabled).map(effectiveRule);
  }

  function pendingReviewCount() {
    return data.rules.filter(rule => rule.enabled && rule.initialStatus === '待人工确认' && !state.manualReviews[rule.ruleId]).length;
  }

  function canFinalizeReview() {
    return pendingReviewCount() === 0;
  }

  function completeReview() {
    if (!hasReviewPermission() || state.taskCompleted || !canFinalizeReview()) return false;
    const rules = reviewRules();
    if (!rules.every(rule => data.finalStatuses.includes(rule.finalStatus))) return false;
    const snapshot = {
      revision: state.reviewRevision,
      completedBy: '陈工',
      completedAt: '今天 17:24',
      systemBasis: Object.fromEntries(rules.map(rule => [rule.ruleId, [rule.evidence, rule.finding].filter(Boolean).join('；')])),
      rules: rules.map(({ ruleId, initialStatus, finalStatus, manualReview }) => ({
        ruleId, initialStatus, finalStatus, manualReview
      }))
    };
    state.completedRevisions.push(JSON.parse(JSON.stringify(snapshot)));
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

  function canExportReview() {
    return hasReviewPermission() && state.taskCompleted && pendingReviewCount() === 0;
  }

  function buildExportRows() {
    if (!canExportReview()) return [];
    const snapshot = state.completedRevisions.at(-1);
    if (!snapshot || !snapshot.rules.every(rule => data.finalStatuses.includes(rule.finalStatus))) return [];
    return snapshot.rules.map(rule => ({
      ruleId: rule.ruleId,
      D: rule.finalStatus === '符合' ? '√' : '',
      E: rule.finalStatus === '不符合' ? '╳' : '',
      F: rule.finalStatus === '不适用' ? '⊙' : '',
      G: [snapshot.systemBasis[rule.ruleId], rule.manualReview?.reason].filter(Boolean).join('；')
    }));
  }

  function applyManualDecision(ruleId, finalStatus, reason, supplementalEvidence = '') {
    const rule = data.rules.find(item => item.ruleId === ruleId);
    const normalizedReason = String(reason || '').trim();
    if (!hasReviewPermission() || state.taskCompleted || !rule || !rule.enabled || !data.finalStatuses.includes(finalStatus) || !normalizedReason) return false;
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

  function selectRule(ruleId) {
    if (!demoMode && state.realTemplate?.rules?.some(rule => rule.rule_id === ruleId)) {
      state.selectedRuleId = ruleId;
      render();
      return;
    }
    if (!data.rules.some(rule => rule.ruleId === ruleId)) return;
    state.selectedRuleId = ruleId;
    render();
  }

  function applyReviewFilter(status) {
    state.filters.status = status;
    const visible = getFilteredRules();
    if (visible.length && !visible.some(rule => rule.ruleId === state.selectedRuleId)) state.selectedRuleId = visible[0].ruleId;
    render();
  }

  function getFilteredRules() {
    const query = state.filters.query.trim().toLowerCase();
    const candidates = state.filters.status === '全部' ? data.rules.map(effectiveRule) : reviewRules();
    return candidates.filter(rule => {
      const statusMatch = state.filters.status === '全部' || rule.displayStatus === state.filters.status;
      const queryMatch = !query || `${rule.ruleId} ${rule.title} ${rule.requirement}`.toLowerCase().includes(query);
      return statusMatch && queryMatch;
    });
  }

  function reviewCounts() {
    return data.statuses.reduce((counts, status) => {
      counts[status] = reviewRules().filter(rule => rule.displayStatus === status).length;
      return counts;
    }, {});
  }

  function evidencePreview(rule) {
    const content = rule.ruleId === 'TR-12' ? `
      <div class="doc-title">X92 PP阶段硬件测试报告</div><div class="doc-meta">项目：X92　版本：A03　阶段：PP</div>
      <div class="doc-line wide"></div><div class="doc-line"></div><div class="doc-line mid"></div>
      <div class="doc-table"><div>测试项</div><div>测量值</div><div>结论</div><div>待机功耗</div><div class="evidence-cell">0.42 W</div><div>符合</div><div>典型功耗</div><div>18.6 W</div><div>符合</div></div>
      <div class="doc-line wide"></div><div class="doc-line mid"></div>
      <div class="evidence-highlight"><span>证据 · 第 28 页 / 测试结论</span><p>整机典型功耗为 16.8 W，测试结果符合设计要求。</p><em>与第 12 页测量值 18.6 W 不一致</em></div>
      <div class="doc-line"></div><div class="doc-line wide"></div>` : `
      <div class="doc-title">X92 PP阶段硬件测试报告</div><div class="doc-meta">当前证据：${escapeHtml(rule.evidence)}</div>
      <div class="doc-line wide"></div><div class="doc-line"></div><div class="doc-line mid"></div>
      <div class="evidence-highlight"><span>证据核对结果</span><p>${escapeHtml(rule.requirement)}</p><em>${escapeHtml(rule.finding || '已匹配到报告或附件中的对应内容')}</em></div>
      <div class="doc-line"></div><div class="doc-line wide"></div><div class="doc-line mid"></div>`;
    return `<div class="document-page">${content}<div class="page-number">28</div></div>`;
  }

  function renderReviewWorkbench() {
    if (!demoMode) return renderRealReview();
    const counts = reviewCounts();
    const pending = pendingReviewCount();
    const rules = getFilteredRules();
    const sourceRules = data.rules.map(effectiveRule);
    const selected = sourceRules.find(rule => rule.ruleId === state.selectedRuleId) || rules[0] || sourceRules[0];
    state.selectedRuleId = selected.ruleId;
    const filters = ['全部', ...data.statuses].map(status => `<button class="filter-chip${state.filters.status === status ? ' is-active' : ''}" data-review-filter="${status}">${status}${status === '全部' ? ` ${sourceRules.length}` : ` ${counts[status] || 0}`}</button>`).join('');
    const list = rules.map(rule => {
      const rowClasses = `rule-row${rule.enabled ? '' : ' source-row-disabled'}${rule.ruleId === selected.ruleId ? ' is-selected' : ''}`;
      const rowMeta = rule.enabled ? `${rule.ruleId} · ${rule.method}` : `${rule.ruleId} · 证据地址 · 不独立执行`;
      return `<button class="${rowClasses}" data-rule="${rule.ruleId}"><span class="rule-seq">${String(rule.seq).padStart(2, '0')}</span><span><b>${escapeHtml(rule.title)}</b><small>${rowMeta}</small></span>${rule.enabled ? resultStatusBadge(rule.displayStatus) : '<span class="read-only">不执行</span>'}</button>`;
    }).join('') || '<div class="empty-state">没有匹配的校验项</div>';
    const gate = pending > 0 ? `disabled aria-disabled="true" title="仍有 ${pending} 项待人工确认"` : '';
    const action = state.taskCompleted
      ? '<button class="btn btn-secondary" data-action="reopen-review">重新打开审核</button><button class="btn btn-primary" data-action="open-export">导出正式审核副本</button>'
      : `<button class="btn btn-primary" data-action="finish-review" ${gate}>完成审核</button>`;
    const manualReviewRecord = selected.manualReview ? `<section class="manual-decision-record"><h3>人工复核记录</h3><dl><div><dt>复核人</dt><dd>${escapeHtml(selected.manualReview.reviewer)}</dd></div><div><dt>复核时间</dt><dd>${escapeHtml(selected.manualReview.reviewedAt)}</dd></div></dl><div><h3>修改原因</h3><p>${escapeHtml(selected.manualReview.reason)}</p></div>${selected.manualReview.supplementalEvidence ? `<div><h3>补充证据</h3><p>${escapeHtml(selected.manualReview.supplementalEvidence)}</p></div>` : ''}</section>` : '';
    const finalStatusOptions = `${selected.finalStatus ? '' : '<option value="" selected disabled>请选择最终状态</option>'}${data.finalStatuses.map(status => `<option value="${status}" ${selected.finalStatus === status ? 'selected' : ''}>${status}</option>`).join('')}`;
    const manualDecisionForm = selected.enabled && hasReviewPermission() && !state.taskCompleted ? `<form class="manual-decision-form"><div class="manual-review-heading"><span>!</span><div><h3>${selected.displayStatus === '待人工确认' ? '需要人工确认' : '人工复核判定'}</h3><p>${selected.displayStatus === '待人工确认' ? '规则审核和 AI 均未形成明确证据结论。' : '可根据人工复核证据调整当前结论。'}</p></div></div><p>${escapeHtml(selected.finding || '请核对已提供材料并给出人工结论。')}</p><label><span>人工最终状态 <b>必填</b></span><select id="manual-final-status" required>${finalStatusOptions}</select></label><label><span>修改原因 <b>必填</b></span><textarea id="manual-review-reason" rows="3" required placeholder="填写人工判断依据">${escapeHtml(selected.manualReview?.reason || '')}</textarea></label><label><span>补充证据 <b>选填</b></span><textarea id="manual-review-evidence" rows="2" placeholder="填写补充证据位置">${escapeHtml(selected.manualReview?.supplementalEvidence || '')}</textarea></label><button type="button" class="btn btn-primary" data-action="save-manual-decision">保存人工判定</button></form>` : '';
    const disabledNotice = selected.enabled ? '' : '<section class="source-row-disabled"><h3>证据地址 · 不独立执行</h3><p>该源行并入 TR-04 作为证据地址，仅供追溯，不形成独立审核结果，也不能提交人工判定。</p></section>';
    return `<div class="review-page">${pageHeader('EVIDENCE REVIEW · A11', '审核结果', `X92 PP阶段硬件测试报告 · ${escapeHtml(state.selectedTaskId)}`, action)}
      <section class="review-summary"><div><span>已形成最终状态</span><strong>${executedRuleCount - pending} / ${executedRuleCount}</strong></div><i></i><div><span>符合</span><strong class="green-text">${counts['符合']}</strong></div><div><span>不符合</span><strong class="red-text">${counts['不符合']}</strong></div><div><span>不适用</span><strong>${counts['不适用']}</strong></div><div><span>待人工确认</span><strong class="amber-text">${pending}</strong></div><p><span>●</span> ${pending > 0 ? `仍有 ${pending} 项待人工复核，暂不能完成和正式导出` : state.taskCompleted ? `第 ${state.reviewRevision} 次审核已完成，可预览正式审核副本` : `第 ${state.reviewRevision} 次审核待完成；完成后可预览正式审核副本`}</p></section>
      <section class="review-toolbar"><div class="filter-row">${filters}</div><label class="search-box"><span>⌕</span><input id="review-search" value="${escapeHtml(state.filters.query)}" placeholder="搜索规则或检查项"></label></section>
      <section class="review-workbench">
        <aside class="rule-list-panel"><div class="column-title"><div><b>A11 校验项</b><small>${baselineLabel}</small></div><span>源序号</span></div><div class="rule-list">${list}</div></aside>
        <article class="evidence-panel"><div class="column-title"><div><b>报告证据</b><small>X92_PP阶段硬件测试报告_A03.docx</small></div><span class="read-only">只读预览</span></div><div class="document-canvas">${evidencePreview(selected)}</div></article>
        <aside class="decision-panel"><div class="column-title"><div><b>问题详情</b><small>${selected.ruleId} · 源序号 ${selected.seq}</small></div>${selected.enabled ? resultStatusBadge(selected.displayStatus) : '<span class="read-only">不执行</span>'}</div><div class="decision-body">
          <div class="decision-title"><small>检查项</small><h2>${escapeHtml(selected.title)}</h2></div>
          ${selected.enabled ? `<section class="decision-status-grid"><div><h3>系统初判</h3>${resultStatusBadge(selected.initialStatus)}</div><div><h3>人工最终状态</h3>${selected.finalStatus ? resultStatusBadge(selected.finalStatus) : '<span class="result-status result-pending"><b>?</b>待人工处理</span>'}</div></section>` : ''}
          ${manualReviewRecord}
          <section><h3>判定依据</h3><p>${escapeHtml(selected.requirement)}</p></section>
          <section class="system-evidence-section"><h3>证据位置</h3><div class="evidence-link"><span>⌖</span><p><b>${escapeHtml(selected.evidence)}</b><small>点击规则时同步切换中间证据预览</small></p></div></section>
          ${selected.enabled && selected.displayStatus === '不符合' ? `<section class="issue-box"><h3>发现的问题</h3><p>${escapeHtml(selected.finding || (selected.ruleId === 'TR-12' ? '测试结论中的典型功耗为 16.8 W，与数据表记录的 18.6 W 不一致。' : '报告内容未满足当前校验要求，请根据证据位置人工核对。'))}</p></section>` : ''}
          ${disabledNotice}${manualDecisionForm}
        </div></aside>
      </section></div>`;
  }

  function openExportDialog() {
    if (!canExportReview()) {
      showToast(hasReviewPermission() ? `请先完成审核；当前仍有 ${pendingReviewCount()} 项待人工确认` : '当前角色没有审核副本导出权限');
      return false;
    }
    const counts = reviewCounts();
    document.getElementById('dialog-root').innerHTML = `<div class="dialog-backdrop"><section class="dialog export-dialog" role="dialog" aria-modal="true" aria-labelledby="export-title"><button class="dialog-close" data-action="close-dialog" aria-label="关闭">×</button><span class="dialog-icon">XLS</span><h2 id="export-title">A11 XLS 审核副本 · 原型预览</h2><p>第 ${state.reviewRevision} 次审核已完成，共 ${buildExportRows().length} 个有效校验项。D/E/F 使用最终状态：符合 √、不符合 ╳、不适用 ⊙；G 包含系统证据、系统判定依据与人工修改原因。</p><div class="export-counts">${data.finalStatuses.map(status => `<div>${resultStatusBadge(status)}<strong>${counts[status] || 0}</strong></div>`).join('')}</div><div class="safety-strip"><span>锁</span><p><strong>不会修改原测试报告</strong>当前仅为原型预览，确认后只显示提示，不会生成文件，也不会覆盖正式 A11 模板。</p></div><div class="export-name"><small>预览文件名</small><b>X92_PP阶段硬件测试报告_A11_审核副本.xls</b></div><div class="dialog-actions"><button class="btn btn-secondary" data-action="close-dialog">取消</button><button class="btn btn-primary" data-action="confirm-export">确认预览</button></div></section></div>`;
    return true;
  }

  function closeDialog() {
    document.getElementById('dialog-root').innerHTML = '';
  }

  function showToast(message) {
    const region = document.getElementById('toast-region');
    region.innerHTML = `<div class="toast"><span>✓</span>${escapeHtml(message)}</div>`;
    window.setTimeout(() => { region.innerHTML = ''; }, 3200);
  }

  function renderTemplateList() {
    if (!demoMode) return renderRealTemplateList();
    const rows = data.templates.map(template => `<tr><td><div class="template-name"><span class="sheet-icon">XLS</span><div><strong>${template.name}</strong><small>${template.id}</small></div></div></td><td><b class="version-tag">${template.version}</b></td><td><strong>${template.effectiveRules}</strong><small>${template.version === 'A11' ? baselineLabel : `${template.sourceRows} 个源行 · ${template.effectiveRules} 个执行项`}</small></td><td>${template.status === '已发布' ? '<span class="status-badge status-success"><b>✓</b>已发布</span>' : '<span class="status-badge status-neutral"><b>—</b>已停用</span>'}</td><td>${template.creator}</td><td>${template.updated}</td><td><button class="table-action" data-action="open-template" data-template="${template.id}">管理</button></td></tr>`).join('');
    return `${pageHeader('TEMPLATE ADMINISTRATION', '模板管理', '上传、发布或停用审核模板，已发布版本不会被直接覆盖。', '<button class="btn btn-primary" data-action="upload-template">＋ 上传模板</button>')}
      ${demoMode ? '' : '<div class="mode-banner is-demo"><b>模板管理模拟</b><span>本页尚未连接模板管理后端；上传、草稿、启停和发布不会持久化。</span></div>'}
      <section class="admin-metrics"><article><span>已发布模板</span><strong>1</strong><small>当前 A11</small></article><article><span>待发布版本</span><strong>${state.templateDraft ? '1' : '0'}</strong><small>${state.templateDraft ? 'A12 草稿' : '暂无草稿'}</small></article><article><span>执行项</span><strong>${executedRuleCount}</strong><small>${baselineLabel}</small></article></section>
      <section class="panel"><div class="panel-heading"><div><h2>审核模板</h2><p>仅“已发布”版本可用于创建审核任务</p></div><label class="search-box"><span>⌕</span><input placeholder="搜索模板或版本"></label></div><div class="table-wrap"><table><thead><tr><th>模板名称</th><th>版本</th><th>有效校验项</th><th>状态</th><th>创建人</th><th>更新时间</th><th></th></tr></thead><tbody>${rows}</tbody></table></div></section>`;
  }

  function templateStatusBadge(status) {
    if (status === 'PUBLISHED') return '<span class="status-badge status-success"><b>✓</b>已发布</span>';
    if (status === 'DRAFT') return '<span class="status-badge status-warning"><b>○</b>待发布</span>';
    return '<span class="status-badge status-neutral"><b>—</b>已停用</span>';
  }

  function renderRealTemplateList() {
    const templates = state.realTemplates || [];
    const rows = templates.map(template => `<tr><td><div class="template-name"><span class="sheet-icon">XLS</span><div><strong>${escapeHtml(template.name)}</strong><small>${escapeHtml(template.source_filename)}</small></div></div></td><td><b class="version-tag">${escapeHtml(template.version)}</b></td><td><strong>${template.effective_rules}</strong><small>${template.source_rows} 个源行 · ${template.effective_rules} 个执行项</small></td><td>${templateStatusBadge(template.status)}</td><td>${escapeHtml(template.created_by)}</td><td>${formatTime(template.updated_at)}</td><td><button class="table-action" data-action="open-real-template" data-template="${escapeHtml(template.id)}">管理</button></td></tr>`).join('');
    const published = templates.filter(item => item.status === 'PUBLISHED').length;
    const drafts = templates.filter(item => item.status === 'DRAFT').length;
    const activeRules = templates.filter(item => item.status === 'PUBLISHED').reduce((total, item) => total + item.effective_rules, 0);
    return `${pageHeader('TEMPLATE ADMINISTRATION', '模板管理', '上传、校验、发布或停用审核模板；源文件与已发布版本不会被覆盖。')}
      ${realErrorPanel()}
      <section class="panel"><div class="panel-heading"><div><h2>上传待发布版本</h2><p>只接受 XLS；目标版本必须与检查表 A2 一致，历史笔误不能作为有效版本。</p></div></div><div class="editor-fields">
        <label class="full"><span>审核模板 XLS</span><input id="template-source-input" type="file" accept=".xls,application/vnd.ms-excel"></label>
        <label><span>模板名称</span><input id="template-name-input" value="硬件测试过程检查单"></label>
        <label><span>目标版本</span><input id="template-version-input" placeholder="例如 A12"></label>
        <label><span>操作人</span><input id="template-actor-input" value="模板管理员"></label>
        <div><button class="btn btn-primary" data-action="upload-real-template" ${state.templateLoading ? 'disabled' : ''}>${state.templateLoading ? '正在处理…' : '上传并校验'}</button></div>
      </div></section>
      <section class="admin-metrics"><article><span>已发布模板</span><strong>${published}</strong><small>可用版本记录</small></article><article><span>待发布版本</span><strong>${drafts}</strong><small>可继续维护</small></article><article><span>已发布执行项</span><strong>${activeRules}</strong><small>当前模板规则总数</small></article></section>
      <section class="panel"><div class="panel-heading"><div><h2>审核模板</h2><p>发布与停用均保留版本和规则历史</p></div></div><div class="table-wrap"><table><thead><tr><th>模板名称</th><th>版本</th><th>有效校验项</th><th>状态</th><th>创建人</th><th>更新时间</th><th></th></tr></thead><tbody>${rows || '<tr><td colspan="7"><div class="empty-state">暂无模板版本</div></td></tr>'}</tbody></table></div></section>`;
  }

  function editorRule(rule) {
    const enabled = Object.hasOwn(state.ruleEnabled, rule.ruleId) ? state.ruleEnabled[rule.ruleId] : rule.enabled;
    return { ...rule, enabled };
  }

  function renderRuleEditor() {
    if (!demoMode) return renderRealRuleEditor();
    const rules = data.rules.map(editorRule);
    const selected = rules.find(rule => rule.ruleId === state.selectedRuleId) || rules[0];
    const list = rules.map(rule => `<button class="editor-rule${rule.ruleId === selected.ruleId ? ' is-selected' : ''}" data-rule="${rule.ruleId}"><span>${String(rule.seq).padStart(2, '0')}</span><div><b>${escapeHtml(rule.title)}</b><small>${rule.ruleId} · ${rule.method}</small></div><em class="${rule.enabled ? 'enabled' : 'disabled'}">${rule.enabled ? '启用' : '停用'}</em></button>`).join('');
    const version = state.templateDraft ? 'A12 草稿' : 'A11 已发布';
    const draftActions = state.templateDraft ? `<button class="btn btn-secondary" data-action="add-rule">＋ 新增校验项</button><button class="btn btn-primary" data-action="publish-template" ${state.publishBlocked ? 'disabled aria-disabled="true"' : ''}>发布版本</button>` : '<button class="btn btn-primary" data-action="create-draft">生成待发布版本</button>';
    const blockerPanel = state.publishBlocked ? `<div class="validation-panel has-errors"><div class="validation-heading"><span>×</span><div><b>发布检查发现问题</b><small>2 项结构问题阻止发布，1 项发布提醒</small></div></div><ul><li><b>规则编号重复</b><span>TR-12 与新增项使用了相同编号，必须修正</span></li><li class="validation-warning"><b>发布提醒：缺少证据定义</b><span>允许发布；该规则将标记为“需人工复核”，审核时进入待人工确认</span></li><li><b>版本不一致</b><span>主表 A12 与修订记录 A11 不一致，必须修正</span></li></ul></div>` : `<div class="validation-panel"><div class="validation-heading"><span>✓</span><div><b>结构校验通过</b><small>固定字段、规则编号与版本记录均有效</small></div></div><ul><li><b>规则编号唯一</b><span>22 / 22 项通过</span></li><li class="validation-warning"><b>发布提醒</b><span>缺少自动判定条件或证据定义的规则仍可发布，并转入待人工确认</span></li><li><b>版本记录一致</b><span>主表与修订记录均为 ${state.templateDraft ? 'A12' : 'A11'}</span></li></ul></div>`;
    return `${pageHeader('RULE EDITOR · A11', '模板规则编辑', `硬件测试过程检查单 · 当前版本 ${version}`, draftActions)}
      ${demoMode ? '' : '<div class="mode-banner is-demo"><b>模板规则模拟</b><span>本页尚未连接模板管理后端；所有修改只在当前页面会话中演示。</span></div>'}
      <section class="editor-banner"><div><span class="sheet-icon">XLS</span><div><small>模板版本</small><strong>${version}</strong></div></div><p>${state.templateDraft ? '当前修改仅作用于草稿，不影响已发布的 A11 和历史任务。' : '已发布版本为只读；生成待发布版本后才可新增、删除或启停校验项。'}</p><span class="status-badge ${state.templateDraft ? 'status-warning' : 'status-success'}"><b>${state.templateDraft ? '○' : '✓'}</b>${state.templateDraft ? '待发布' : '已发布'}</span></section>
      <section class="rule-editor-layout"><aside class="editor-list panel"><div class="column-title"><div><b>A11 源行</b><small>${baselineLabel}</small></div><span>状态</span></div><div>${list}</div></aside>
        <article class="editor-form panel"><div class="column-title"><div><b>规则详情</b><small>${selected.ruleId} · 源序号 ${selected.seq}</small></div><button class="toggle ${selected.enabled ? 'is-on' : ''}" data-action="toggle-rule" data-rule="${selected.ruleId}" ${state.templateDraft ? '' : 'disabled'} aria-label="${selected.enabled ? '停用' : '启用'}当前规则"><span></span>${selected.enabled ? '启用' : '停用'}</button></div><div class="editor-fields">
          <label><span>检查项名称</span><input value="${escapeHtml(selected.title)}" ${state.templateDraft ? '' : 'readonly'}></label><label><span>规则编号</span><input value="${selected.ruleId}" readonly></label>
          <label class="full"><span>检查项原文 / 原子校验要求</span><textarea rows="4" ${state.templateDraft ? '' : 'readonly'}>${escapeHtml(selected.requirement)}</textarea></label><label class="full"><span>所需证据</span><textarea rows="3" ${state.templateDraft ? '' : 'readonly'}>${escapeHtml(selected.evidence)}</textarea></label>
          <label><span>主判定方式</span><select ${state.templateDraft ? '' : 'disabled'}><option selected>${selected.method}</option><option>规则</option><option>AI</option><option>规则+AI</option><option>需人工复核</option></select></label><label><span>导出映射</span><input value="人工复核完成后，最终状态写入 D/E/F，证据与复核说明写入 G" readonly></label>
          ${state.templateDraft ? '<div class="editor-danger full"><p><b>删除校验项</b><span>仅从当前待发布版本移除，不影响 A11。</span></p><button class="btn btn-danger" data-action="delete-rule">删除</button></div>' : ''}
        </div></article><aside class="validation-column">${blockerPanel}<button class="simulate-link" data-action="toggle-blockers">${state.publishBlocked ? '恢复通过状态' : '演示发布阻塞状态'}</button></aside></section>`;
  }

  function judgmentLabel(value) {
    return ({ RULE: '规则', RULE_PLUS_AI: '规则+AI', AI: 'AI', MANUAL: '需人工复核', DISABLED: '不执行' })[value] || value;
  }

  function renderRealRuleEditor() {
    if (state.templateLoading && !state.realTemplate) return `${pageHeader('RULE EDITOR', '模板规则编辑', '正在加载模板版本。')}<section class="panel placeholder"><h2>正在加载</h2></section>`;
    if (!state.realTemplate) return `${pageHeader('RULE EDITOR', '模板规则编辑', '请从模板管理选择一个版本。')}${realErrorPanel()}<section class="panel placeholder"><button class="btn btn-secondary" data-nav="templates">返回模板管理</button></section>`;
    const template = state.realTemplate.template;
    const rules = state.realTemplate.rules || [];
    const selected = selectedRealTemplateRule();
    const editable = template.status === 'DRAFT';
    const list = rules.map(rule => `<button class="editor-rule${rule.rule_id === selected?.rule_id ? ' is-selected' : ''}" data-rule="${escapeHtml(rule.rule_id)}"><span>${String(rule.source_sequence).padStart(2, '0')}</span><div><b>${escapeHtml(rule.summary)}</b><small>${escapeHtml(rule.rule_id)} · ${judgmentLabel(rule.main_judgment)}</small></div><em class="${rule.enabled ? 'enabled' : 'disabled'}">${rule.enabled ? '启用' : '停用'}</em></button>`).join('');
    const findings = (template.validation_findings || []).map(item => `<li class="${item.severity === 'WARNING' ? 'validation-warning' : ''}"><b>${escapeHtml(item.code)}</b><span>${escapeHtml(item.message)}${item.structural_address ? ` · ${escapeHtml(item.structural_address)}` : ''}</span></li>`).join('');
    const blockers = (template.validation_findings || []).filter(item => item.severity === 'ERROR').length;
    const actions = editable
      ? `<button class="btn btn-secondary" data-action="add-real-rule">＋ 新增校验项</button><button class="btn btn-primary" data-action="publish-real-template" ${blockers ? 'disabled aria-disabled="true"' : ''}>发布版本</button>`
      : template.status === 'PUBLISHED' ? '<button class="btn btn-secondary" data-action="retire-real-template">停用版本</button>' : '';
    const selectedForm = selected ? `<article class="editor-form panel"><div class="column-title"><div><b>规则详情</b><small>${escapeHtml(selected.rule_id)} · 来源序号 ${selected.source_sequence}</small></div><button class="toggle ${selected.enabled ? 'is-on' : ''}" data-action="toggle-real-rule" data-rule="${escapeHtml(selected.rule_id)}" ${editable ? '' : 'disabled'} aria-label="${selected.enabled ? '停用' : '启用'}当前规则"><span></span>${selected.enabled ? '启用' : '停用'}</button></div><div class="editor-fields">
      <label><span>检查项名称</span><input id="template-rule-summary" value="${escapeHtml(selected.summary)}" ${editable ? '' : 'readonly'}></label><label><span>规则编号</span><input value="${escapeHtml(selected.rule_id)}" readonly></label>
      <label class="full"><span>可验证要求</span><textarea id="template-rule-requirement" rows="4" ${editable ? '' : 'readonly'}>${escapeHtml(selected.verifiable_requirement)}</textarea></label>
      <label class="full"><span>所需材料</span><textarea id="template-rule-materials" rows="3" ${editable ? '' : 'readonly'}>${escapeHtml(selected.required_materials)}</textarea></label>
      <label><span>主判定方式</span><select id="template-rule-judgment" ${editable ? '' : 'disabled'}>${['RULE','RULE_PLUS_AI','AI','MANUAL','DISABLED'].map(value => `<option value="${value}" ${selected.main_judgment === value ? 'selected' : ''}>${judgmentLabel(value)}</option>`).join('')}</select></label>
      <label class="full"><span>确认边界</span><textarea id="template-rule-boundary" rows="3" ${editable ? '' : 'readonly'}>${escapeHtml(selected.confirmed_boundary)}</textarea></label>
      ${editable ? `<div class="full dialog-actions"><button class="btn btn-danger" data-action="delete-real-rule" data-rule="${escapeHtml(selected.rule_id)}">删除</button><button class="btn btn-primary" data-action="save-real-rule">保存规则</button></div>` : ''}
      </div></article>` : '<article class="editor-form panel"><div class="empty-state">当前版本没有规则</div></article>';
    return `${pageHeader(`RULE EDITOR · ${escapeHtml(template.version)}`, '模板规则编辑', `${escapeHtml(template.name)} · ${template.source_rows} 个源行 · ${template.effective_rules} 个执行项`, actions)}${realErrorPanel()}
      <section class="editor-banner"><div><span class="sheet-icon">XLS</span><div><small>模板版本</small><strong>${escapeHtml(template.version)}</strong></div></div><p>${editable ? '当前修改只作用于草稿；上传源文件和已发布版本保持不变。' : '该版本为只读；停用只改变可用状态，不删除历史。'}</p>${templateStatusBadge(template.status)}</section>
      <section class="rule-editor-layout"><aside class="editor-list panel"><div class="column-title"><div><b>校验项</b><small>${rules.length} 个规则记录</small></div><span>状态</span></div><div>${list || '<div class="empty-state">暂无规则</div>'}</div></aside>${selectedForm}<aside class="validation-column"><div class="validation-panel${blockers ? ' has-errors' : ''}"><div class="validation-heading"><span>${blockers ? '×' : '✓'}</span><div><b>${blockers ? '发布检查发现问题' : '结构校验可发布'}</b><small>${blockers} 项阻塞，${(template.validation_findings || []).length - blockers} 项提醒</small></div></div><ul>${findings || '<li><b>未发现问题</b><span>当前结构校验通过</span></li>'}</ul></div></aside></section>`;
  }

  function toggleRule(ruleId) {
    if (!hasTemplatePermission() || !state.templateDraft) return false;
    const sourceRule = data.rules.find(item => item.ruleId === ruleId);
    if (!sourceRule) return false;
    const rule = editorRule(sourceRule);
    state.ruleEnabled[ruleId] = !rule.enabled;
    render();
    return true;
  }

  function createDraftVersion() {
    if (!hasTemplatePermission() || state.templateDraft) return false;
    state.templateDraft = true;
    render();
    showToast('已生成 A12 待发布版本，A11 保持不变');
    return true;
  }

  function publishTemplate() {
    if (!hasTemplatePermission() || !state.templateDraft || state.publishBlocked) return false;
    state.templateDraft = false;
    showToast('原型演示：新版本已发布');
    render();
    return true;
  }

  function renderPlaceholder() {
    const titles = {
      'create-task': ['CREATE REVIEW TASK', '创建审核任务', '按照步骤上传报告与支撑证据。'],
      review: ['EVIDENCE REVIEW', '审核结果', '逐项核对问题、证据与人工处理结果。'],
      templates: ['TEMPLATE ADMIN', '模板管理', '维护审核模板的版本及发布状态。'],
      'rule-editor': ['RULE EDITOR', '模板规则编辑', '查看并维护 A11 校验项。']
    };
    const [kicker, title, text] = titles[state.view];
    return `${pageHeader(kicker, title, text)}<section class="panel placeholder"><span>构</span><h2>${title}</h2><p>该页面将在下一实现步骤中接入完整交互。</p><button class="btn btn-secondary" data-nav="dashboard">返回工作台</button></section>`;
  }

  function render() {
    renderSidebar();
    const content = state.view === 'dashboard' ? renderDashboard() : state.view === 'tasks' ? renderTasks() : state.view === 'create-task' ? renderCreateTask() : state.view === 'review' ? renderReviewWorkbench() : state.view === 'templates' ? renderTemplateList() : state.view === 'rule-editor' ? renderRuleEditor() : renderPlaceholder();
    main.innerHTML = demoMode ? content.replace('</header>', `</header>${renderModeBanner()}`) : content;
  }

  document.addEventListener('click', async event => {
    const action = event.target.closest('[data-action]');
    if (action) {
      if (!demoMode) {
        if (action.dataset.action === 'open-real-task') return openRealTask(action.dataset.task, 'tasks');
        if (action.dataset.action === 'open-real-review') { stopPolling(); state.view = 'review'; render(); return; }
        if (action.dataset.action === 'create-real-task') return createRealTask();
        if (action.dataset.action === 'select-real-template') { state.createTemplateId = action.dataset.template; render(); return; }
        if (action.dataset.action === 'save-real-decision') return saveRealDecision();
        if (action.dataset.action === 'complete-real-task') return completeRealTask();
        if (action.dataset.action === 'reopen-real-task') return reopenRealTask();
        if (action.dataset.action === 'open-real-template') return openRealTemplate(action.dataset.template);
        if (action.dataset.action === 'upload-real-template') return uploadRealTemplate();
        if (action.dataset.action === 'save-real-rule') return saveRealTemplateRule();
        if (action.dataset.action === 'toggle-real-rule') return toggleRealTemplateRule(action.dataset.rule);
        if (action.dataset.action === 'add-real-rule') return addRealTemplateRule();
        if (action.dataset.action === 'delete-real-rule') return deleteRealTemplateRule(action.dataset.rule);
        if (action.dataset.action === 'publish-real-template') return publishRealTemplate();
        if (action.dataset.action === 'retire-real-template') return retireRealTemplate();
      }
      if (action.dataset.action === 'demo-upload') state.reportUploaded = true;
      if (action.dataset.action === 'remove-report') state.reportUploaded = false;
      if (action.dataset.action === 'wizard-next') return advanceCreateStep();
      if (action.dataset.action === 'wizard-back') state.createStep = Math.max(1, state.createStep - 1);
      if (action.dataset.action === 'create-demo-task') return createDemoTask();
      if (action.dataset.action === 'finish-review') {
        const completed = completeReview();
        showToast(completed ? '审核已完成，可以预览正式审核副本' : `未完成审核：请确认审核权限、任务状态及剩余 ${pendingReviewCount()} 项待人工确认`);
        return;
      }
      if (action.dataset.action === 'reopen-review') {
        const reopened = reopenReview();
        showToast(reopened ? `已重新打开审核，当前为第 ${state.reviewRevision} 次审核，历史快照已保留` : '当前角色或任务状态不允许重新打开审核');
        return;
      }
      if (action.dataset.action === 'open-export') return openExportDialog();
      if (action.dataset.action === 'save-manual-decision') {
        const statusInput = document.getElementById('manual-final-status');
        const reasonInput = document.getElementById('manual-review-reason');
        const evidenceInput = document.getElementById('manual-review-evidence');
        const success = applyManualDecision(state.selectedRuleId, statusInput ? statusInput.value : '', reasonInput ? reasonInput.value : '', evidenceInput ? evidenceInput.value : '');
        showToast(success ? `人工判定已保存为${statusInput.value}` : '请选择最终状态并填写修改原因后再提交');
        return;
      }
      if (action.dataset.action === 'close-dialog') return closeDialog();
      if (action.dataset.action === 'confirm-export') { closeDialog(); showToast('原型预览结束，未生成任何文件'); return; }
      if (action.dataset.action === 'upload-template') { showToast('原型演示：模板上传入口已触发'); return; }
      if (action.dataset.action === 'open-template') { state.selectedRuleId = 'TR-01'; return navigate('rule-editor'); }
      if (action.dataset.action === 'create-draft') return createDraftVersion();
      if (action.dataset.action === 'toggle-rule') return toggleRule(action.dataset.rule);
      if (action.dataset.action === 'publish-template') return publishTemplate();
      if (action.dataset.action === 'toggle-blockers') { state.publishBlocked = !state.publishBlocked; render(); return; }
      if (action.dataset.action === 'add-rule') { state.publishBlocked = true; render(); showToast('已添加演示校验项，请先完成结构校验'); return; }
      if (action.dataset.action === 'delete-rule') { showToast('原型演示：校验项将从待发布版本删除'); return; }
      if (action.dataset.action === 'toggle-evidence') {
        const evidence = action.dataset.evidence;
        state.selectedEvidence = state.selectedEvidence.includes(evidence) ? state.selectedEvidence.filter(item => item !== evidence) : [...state.selectedEvidence, evidence];
      }
      render();
      return;
    }
    const target = event.target.closest('[data-nav]');
    if (target) {
      if (target.dataset.task) state.selectedTaskId = target.dataset.task;
      navigate(target.dataset.nav);
    }
    const ruleTarget = event.target.closest('[data-rule]');
    if (ruleTarget && !ruleTarget.dataset.action) selectRule(ruleTarget.dataset.rule);
    const filterTarget = event.target.closest('[data-review-filter]');
    if (filterTarget) applyReviewFilter(filterTarget.dataset.reviewFilter);
  });
  document.addEventListener('change', event => {
    if (event.target.id === 'role-select') return setRole(event.target.value);
    if (demoMode) return;
    if (event.target.id === 'primary-report-input') {
      state.primaryReport = event.target.files && event.target.files[0] ? event.target.files[0] : null;
      state.realError = null;
      render();
      return;
    }
    if (event.target.id === 'supporting-files-input') {
      state.supportingFiles = Array.from(event.target.files || []).map(file => ({ file, evidenceKinds: [] }));
      state.realError = null;
      render();
      return;
    }
    if (event.target.dataset && event.target.dataset.supportKind) {
      const item = state.supportingFiles[Number(event.target.dataset.index)];
      if (!item) return;
      const kind = event.target.dataset.supportKind;
      item.evidenceKinds = event.target.checked ? [...new Set([...item.evidenceKinds, kind])] : item.evidenceKinds.filter(value => value !== kind);
      state.realError = null;
      render();
    }
  });
  document.addEventListener('input', event => {
    if (event.target.id === 'review-search') {
      state.filters.query = event.target.value;
      const selectionStart = event.target.selectionStart;
      render();
      const input = document.getElementById('review-search');
      if (input) { input.focus(); input.setSelectionRange(selectionStart, selectionStart); }
    }
  });

  window.prototypeApp = { getState, currentRole, hasReviewPermission, hasTemplatePermission, canNavigate, navigate, setRole, selectRule, applyReviewFilter, effectiveRule, reviewRules, pendingReviewCount, reviewCounts, canFinalizeReview, applyManualDecision, completeReview, reopenReview, canExportReview, buildExportRows, openExportDialog, toggleRule, createDraftVersion, publishTemplate, demoMode, stopPolling, refreshRealTasks, openRealTask, refreshRealTemplates, openRealTemplate };
  render();
  if (!demoMode) refreshRealTasks();
}());
