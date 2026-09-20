import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useTemplateStore } from './templates'

describe('template store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('exposes only published templates for creating tasks', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ templates: [
      { id: 'a', status: 'DRAFT' }, { id: 'b', status: 'PUBLISHED' }, { id: 'c', status: 'RETIRED' },
    ] }), { status: 200 })))
    const store = useTemplateStore()
    await store.loadTemplates()
    expect(store.publishedTemplates.map((item) => item.id)).toEqual(['b'])

    vi.stubGlobal('fetch', vi.fn().mockImplementation(async (input) => {
      const path = String(input)
      if (path.endsWith('/api/templates/a/audit-events')) {
        return new Response(JSON.stringify({ events: [{
          id: 'event-1', template_id: 'a', template_version: 'A12',
          action: 'TEMPLATE_UPLOADED', rule_id: null, actor: '模板规则管理',
          occurred_at: '2026-09-18T00:00:00Z', before: null,
          after: { version: 'A12', status: 'DRAFT' },
        }] }), { status: 200 })
      }
      return new Response(JSON.stringify({
        template: { id: 'a', status: 'DRAFT', validation_findings: [] }, rules: [],
      }), { status: 200 })
    }))
    await store.loadTemplate('a')
    expect(store.auditEvents.map((item) => item.action)).toEqual(['TEMPLATE_UPLOADED'])
  })
})
