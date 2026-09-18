(function () {
  const rules = [
    { ruleId: 'TR-01', seq: 1, sourceRow: 10, title: 'JIRA项目及链接', method: '规则', requirement: 'JIRA项目已建立，报告包含批准格式的项目问题主界面链接。', evidence: 'JIRA项目页面截图、报告第1页', initialStatus: '符合', enabled: true },
    { ruleId: 'TR-02', seq: 2, sourceRow: 13, title: '上阶段问题确认及回归', method: '规则+AI', requirement: '上阶段问题状态已确认，需要回归的问题存在回归记录。', evidence: '上阶段问题清单、回归测试记录', finding: '缺少必需证据：未提供上阶段问题清单和回归测试记录。', initialStatus: '不符合', enabled: true },
    { ruleId: 'TR-03', seq: 3, sourceRow: 14, title: '软件相关问题处理', method: '规则+AI', requirement: '软件相关FAIL已登记并包含处理、软件测试团队经理评审关闭及通知记录。', evidence: 'JIRA-4281、评审纪要附件', initialStatus: '不符合', enabled: true },
    { ruleId: 'TR-04', seq: 4, sourceRow: 15, title: '功耗记录', method: '规则', requirement: '典型工作功耗和待机功耗均已记录。', evidence: '报告第12页、功耗记录截图', initialStatus: '符合', enabled: true },
    { ruleId: 'TR-05', seq: 5, sourceRow: 16, title: '共享路径', method: '不执行', requirement: '源内容仅为共享路径，作为TR-04证据地址。', evidence: '并入TR-04', initialStatus: '不适用', enabled: false },
    { ruleId: 'TR-06', seq: 6, sourceRow: 17, title: '委外测试安排', method: '规则+AI', requirement: '内部无法执行的测试已说明原因并安排委外。', evidence: '测试需求清单、委外安排证明', initialStatus: '不适用', enabled: true },
    { ruleId: 'TR-07', seq: 7, sourceRow: 18, title: '报告版本及命名', method: '规则', requirement: '报告版本、文件名及报告内项目阶段信息一致。', evidence: '文件名、报告首页', initialStatus: '符合', enabled: true },
    { ruleId: 'TR-08', seq: 8, sourceRow: 19, title: '首页填写', method: '规则+AI', requirement: '首页必填字段完整且与正文一致。', evidence: '报告第1页、第3页', initialStatus: '不符合', enabled: true },
    { ruleId: 'TR-09', seq: 9, sourceRow: 20, title: '测试用例选择', method: '规则', requirement: '机型和区域对应的必选用例没有遗漏。', evidence: '用例对应表、报告第4页', initialStatus: '符合', enabled: true },
    { ruleId: 'TR-10', seq: 10, sourceRow: 21, title: '测试数据完整性', method: '规则', requirement: '每个应测项都有记录，未执行项有原因。', evidence: '报告第5—18页', initialStatus: '符合', enabled: true },
    { ruleId: 'TR-11', seq: 11, sourceRow: 22, title: '数据与原始记录一致', method: '规则', requirement: '报告数值格式有效并与原始记录一致。', evidence: '原始记录扫描件第2页、报告第8页', initialStatus: '符合', enabled: true },
    { ruleId: 'TR-12', seq: 12, sourceRow: 23, title: '小结和结论一致', method: '规则+AI', requirement: '小结引用的数据存在，最终结论与数据和小结一致。', evidence: '报告第12页数据表、报告第28页结论', initialStatus: '不符合', enabled: true },
    { ruleId: 'TR-13', seq: 13, sourceRow: 24, title: '问题无漏写漏总结', method: 'AI', requirement: '原始记录中的问题进入问题清单并在结论中得到处理。', evidence: '原始记录、问题清单、报告第28页', finding: '缺少必需证据：未提供完整原始记录，无法核对问题是否全部进入结论。', initialStatus: '不符合', enabled: true },
    { ruleId: 'TR-14', seq: 14, sourceRow: 25, title: 'EMC报告及JIRA处理', method: '规则+AI', requirement: '需要EMC时已提供报告、满足余量并完成问题登记。', evidence: 'EMC报告、JIRA导出记录', initialStatus: '符合', enabled: true },
    { ruleId: 'TR-15', seq: 15, sourceRow: 26, title: '各阶段报告衔接', method: '规则+AI', requirement: '当前结论与历史阶段记录不存在未解释冲突。', evidence: 'DS、PP阶段报告', initialStatus: '符合', enabled: true },
    { ruleId: 'TR-16', seq: 16, sourceRow: 27, title: '结论重点及顺序', method: '规则+AI', requirement: '报告明确突出需要关注的问题并采用可解释顺序。', evidence: '报告第28—29页', finding: '材料已提供，但模板未定义问题排序依据，规则与AI均不能形成有证据支持的明确结论。', initialStatus: '待人工确认', enabled: true },
    { ruleId: 'TR-17', seq: 17, sourceRow: 28, title: '问题表述完整', method: 'AI', requirement: '问题包含对象、条件、现象、实际结果。', evidence: '报告第26页问题列表', initialStatus: '不符合', enabled: true },
    { ruleId: 'TR-18', seq: 18, sourceRow: 29, title: '单条结论目标单一', method: 'AI', requirement: '每条结论只表达一个可独立处理的问题。', evidence: '报告第28页结论', initialStatus: '符合', enabled: true },
    { ruleId: 'TR-19', seq: 19, sourceRow: 30, title: 'CA卡工装温升测试', method: '规则', requirement: '适用CA卡工装时存在温升测试记录和结果。', evidence: '产品适用性说明、温升记录', initialStatus: '不适用', enabled: true },
    { ruleId: 'TR-20', seq: 20, sourceRow: 31, title: 'PP阶段开关机自动化', method: '规则', requirement: 'PP阶段存在开关机自动化测试记录和结果。', evidence: '自动化测试记录附件', initialStatus: '符合', enabled: true },
    { ruleId: 'TR-21', seq: 21, sourceRow: 32, title: 'WIFI结论填写', method: '规则', requirement: 'WIFI报告小结论和页面顶端结论均非空。', evidence: 'WIFI报告第1页、第9页', initialStatus: '符合', enabled: true },
    { ruleId: 'TR-22', seq: 22, sourceRow: 33, title: '温升测试部件喷漆状态', method: '规则+AI', requirement: '证据可识别两类部件喷漆状态并与批准要求比对。', evidence: '温升照片附件、喷漆要求', finding: '缺少必需证据：未提供温升照片附件和批准的喷漆要求。', initialStatus: '不符合', enabled: true }
  ];

  window.DEMO_DATA = Object.freeze({
    roles: Object.freeze([
      { id: 'tester', label: '测试报告审核', canReview: true, canManageTemplates: false },
      { id: 'admin', label: '模板规则管理', canReview: false, canManageTemplates: true },
      { id: 'combined', label: '测试报告审核 + 模板规则管理', canReview: true, canManageTemplates: true }
    ]),
    statuses: Object.freeze(['符合', '不符合', '不适用', '待人工确认']),
    initialStatuses: Object.freeze(['符合', '不符合', '不适用', '待人工确认']),
    finalStatuses: Object.freeze(['符合', '不符合', '不适用']),
    supportedInputFormats: Object.freeze(['PDF', 'DOC', 'DOCX', 'XLS', 'XLSX']),
    tasks: Object.freeze([
      { id: 'TASK-2026-092', name: 'X92 PP阶段硬件测试报告', template: 'A11', status: '待人工复核', progress: '21/21', updated: '今天 16:42', owner: '陈工' },
      { id: 'TASK-2026-091', name: 'M8 EMC摸底测试报告', template: 'A11', status: '审核中', progress: '14/21', updated: '今天 15:18', owner: '李工' },
      { id: 'TASK-2026-089', name: 'K6 温升测试报告', template: 'A11', status: '已结束', progress: '21/21', updated: '昨天 17:05', owner: '王工' }
    ]),
    rules: Object.freeze(rules.map(rule => Object.freeze(rule))),
    templates: Object.freeze([
      { id: 'TPL-A11', name: '硬件测试过程检查单', version: 'A11', effectiveRules: 21, sourceRows: 22, status: '已发布', creator: '张敏', updated: '2026-09-07 14:30' },
      { id: 'TPL-A10', name: '硬件测试过程检查单', version: 'A10', effectiveRules: 20, sourceRows: 21, status: '已停用', creator: '张敏', updated: '2025-11-18 09:42' }
    ])
  });
}());
