import { fireEvent, render, screen } from '@testing-library/vue'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ReviewView from './ReviewView.vue'

const rule = {
  id: 'rule-1', template_id: 'template-a11', rule_id: 'TR-01', source_row: 12, source_sequence: 1,
  summary: 'JIRA项目及链接', verifiable_requirement: '报告中必须提供可追溯的JIRA链接', required_materials: 'JIRA记录',
  main_judgment: 'RULE', confirmed_boundary: '只校验可追溯字段', enabled: true,
  created_at: '2026-09-17T00:00:00Z', updated_at: '2026-09-17T00:00:00Z',
}
const result = {
  id: 'result-1', task_id: 'task-1', rule_id: 'TR-01', initial_status: 'COMPLIANT', basis_code: 'FOUND',
  basis_text: 'Every applicable deterministic obligation is positively evidenced.', evidence_locators: [], missing_materials: [],
  unresolved_semantics: [], engine_version: 'engine', baseline_version: 'A11', active_revision_no: 0,
  created_at: '2026-09-17T00:01:00Z',
}
const decision = {
  id: 'decision-1', rule_result_id: 'result-1', final_status: 'NON_COMPLIANT', reason: '人工复核发现链接无效',
  supplemental_evidence: [], actor: '审核员A', decided_at: '2026-09-17T00:02:00Z',
}
const task = {
  id: 'task-1', state: 'COMPLETED', active_revision_no: 0, display_name: 'report.xls', template_id: 'template-a11',
  template_name: '硬件测试过程检查单', template_version: 'A11', template_rule_count: 1, template_rules: [rule],
  created_at: '2026-09-17T00:00:00Z', updated_at: '2026-09-17T00:03:00Z', source_files: [], stage_failures: [],
  rule_results: [result], manual_decisions: [decision], revisions: [{
    id: 'revision-1', task_id: 'task-1', revision_no: 1, completed_at: '2026-09-17T00:03:00Z', result_snapshot: '{}',
    snapshot: { task_id: 'task-1', revision_no: 1, template_id: 'template-a11', template_name: '硬件测试过程检查单',
      template_version: 'A11', template_source_sha256: 'abc', template_rules: [rule], results: [result], decisions: [decision] },
  }],
}

async function renderView() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/tasks/:taskId/review', component: ReviewView }] })
  await router.push('/tasks/task-1/review')
  await router.isReady()
  return render(ReviewView, { global: { plugins: [createPinia(), router] } })
}

describe('review result transparency and history', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(task), { status: 200 })))
  })

  it('shows the system status beside the human final status and frozen rule context', async () => {
    await renderView()

    expect(await screen.findByText('JIRA项目及链接')).toBeTruthy()
    expect(screen.getByText('系统初判')).toBeTruthy()
    expect(screen.getByText('人工最终状态')).toBeTruthy()
    expect(screen.getByText('规则匹配')).toBeTruthy()
    expect(screen.getByText('报告中必须提供可追溯的JIRA链接')).toBeTruthy()
    expect(screen.getByText(/审核员A/)).toBeTruthy()
  })

  it('opens a completed revision in read-only mode', async () => {
    await renderView()
    await fireEvent.click(await screen.findByRole('button', { name: /第 1 版/ }))

    expect(screen.getByRole('heading', { name: '历史修订 · 第 1 版' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: '保存人工判定' })).toBeNull()
  })
})
