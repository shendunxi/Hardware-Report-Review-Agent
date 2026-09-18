import { describe, expect, it } from 'vitest'

import type { ReviewTask } from './types'
import { deriveReviewRows, deriveRevisionRows, localizeReviewText, unresolvedReviewCount } from './review'

const task: ReviewTask = {
  id: 'task-1', state: 'READY_FOR_REVIEW', active_revision_no: 0,
  display_name: 'report.xls', template_id: 'template-a11', template_name: '硬件测试过程检查单',
  template_version: 'A11', template_rule_count: 2,
  created_at: '2026-09-17T00:00:00Z', updated_at: '2026-09-17T00:01:00Z',
  source_files: [], stage_failures: [], revisions: [],
  template_rules: [
    {
      id: 'rule-1', template_id: 'template-a11', rule_id: 'TR-01', source_row: 12, source_sequence: 1,
      summary: 'JIRA项目及链接', verifiable_requirement: '报告中提供有效JIRA链接', required_materials: 'JIRA记录',
      main_judgment: 'RULE', confirmed_boundary: '只验证可追溯字段', enabled: true,
      created_at: '2026-09-17T00:00:00Z', updated_at: '2026-09-17T00:00:00Z',
    },
  ],
  rule_results: [
    {
      id: 'result-1', task_id: 'task-1', rule_id: 'TR-01', initial_status: 'COMPLIANT',
      basis_code: 'FOUND', basis_text: '存在明确证据', evidence_locators: [], missing_materials: [],
      unresolved_semantics: [], engine_version: 'engine', baseline_version: 'A11', active_revision_no: 0,
      created_at: '2026-09-17T00:01:00Z',
    },
    {
      id: 'result-2', task_id: 'task-1', rule_id: 'TR-16', initial_status: 'NEEDS_REVIEW',
      basis_code: 'SEMANTIC', basis_text: '需要人工确认', evidence_locators: [], missing_materials: [],
      unresolved_semantics: ['排序标准不明确'], engine_version: 'engine', baseline_version: 'A11', active_revision_no: 0,
      created_at: '2026-09-17T00:01:00Z',
    },
  ],
  manual_decisions: [
    {
      id: 'decision-1', rule_result_id: 'result-1', final_status: 'NON_COMPLIANT',
      reason: '人工确认不符合', supplemental_evidence: [], actor: 'local-review',
      decided_at: '2026-09-17T00:02:00Z',
    },
  ],
}

describe('review derivation', () => {
  it('keeps system status and lets the human final status win for display', () => {
    const rows = deriveReviewRows(task)

    expect(rows[0]).toMatchObject({
      ruleId: 'TR-01', initialStatus: 'COMPLIANT', finalStatus: 'NON_COMPLIANT', displayStatus: 'NON_COMPLIANT',
      rule: { summary: 'JIRA项目及链接', main_judgment: 'RULE' },
    })
    expect(rows[1]).toMatchObject({
      ruleId: 'TR-16', initialStatus: 'NEEDS_REVIEW', finalStatus: null, displayStatus: 'NEEDS_REVIEW',
    })
  })

  it('counts only unresolved needs-review results', () => {
    expect(unresolvedReviewCount(task)).toBe(1)
  })

  it('localizes historical English diagnostics without changing audit codes', () => {
    expect(localizeReviewText('A required material is missing or an objective check has failed. Atomic bases: FIELD_VERSION_MISSING.'))
      .toBe('缺少必需材料，或某项客观校验未通过。判定明细代码：FIELD_VERSION_MISSING。')
  })

  it('derives read-only rows from an immutable completed revision', () => {
    const rows = deriveRevisionRows({
      task_id: 'task-1', revision_no: 1, template_id: 'template-a11', template_name: '硬件测试过程检查单',
      template_version: 'A11', template_source_sha256: 'abc', template_rules: task.template_rules,
      results: task.rule_results, decisions: task.manual_decisions,
    })

    expect(rows[0]).toMatchObject({
      ruleId: 'TR-01', initialStatus: 'COMPLIANT', finalStatus: 'NON_COMPLIANT', displayStatus: 'NON_COMPLIANT',
      rule: { verifiable_requirement: '报告中提供有效JIRA链接' },
    })
  })

  it('keeps legacy revision snapshots readable when rule context was not stored', () => {
    const rows = deriveRevisionRows({
      task_id: 'task-1', revision_no: 1, template_id: 'template-a11', template_name: '硬件测试过程检查单',
      template_version: 'A11', template_source_sha256: 'abc',
      results: task.rule_results, decisions: task.manual_decisions,
    })

    expect(rows[0]).toMatchObject({
      ruleId: 'TR-01', initialStatus: 'COMPLIANT', finalStatus: 'NON_COMPLIANT', rule: null,
    })
  })
})
